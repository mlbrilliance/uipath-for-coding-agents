"""Wrapper around the UiPath Python SDK + `uipath` CLI.

Centralizes:
    - Token-aware SDK construction (uses aurora.auth.ensure_fresh_token)
    - Scoped helpers — folders, jobs, queues, assets, tasks, processes, Maestro
    - `uipath` CLI shellouts (init, run, pack, publish) with sane error handling

Most agents and daemons reach the platform through this module. Direct
imports of `uipath` are discouraged outside this file so we have one place
to swap SDK versions or add tracing.
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any, cast

import httpx

from aurora.auth import ensure_fresh_token

logger = logging.getLogger(__name__)

PUBLISH_FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "maestro" / "publish_request.json"
PUBLISH_MAX_RETRIES = 3
PUBLISH_RETRY_BASE_DELAY = 1.0  # seconds; doubles each retry


@dataclass(frozen=True)
class FolderRef:
    name: str
    id: int


class UiPathClient:
    """Thin wrapper around `uipath.UiPath` + `uipath` CLI.

    The actual UiPath SDK class is imported lazily so tests / mocks don't
    have to install the full uipath package up front.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        folder: str | None = None,
        dotenv_path: Path | None = None,
    ):
        self.url = url or os.environ.get("UIPATH_URL")
        self.folder = folder or os.environ.get("UIPATH_FOLDER")
        self.dotenv_path = dotenv_path
        if not self.url:
            raise RuntimeError("UIPATH_URL not set")
        self._sdk: Any = None

    # ---------- SDK lifecycle ----------

    @property
    def sdk(self) -> Any:
        """Lazily-initialised uipath SDK. Refreshes the token before each access
        if the cached one is stale.

        NOTE: We mostly bypass `sdk.api_client` for raw OData/Maestro/Tasks
        calls because its built-in `request()` method does scoped URL
        rewriting that mangles `/odata/...` paths (and individual typed
        services like `sdk.folders` route through `/api/...` endpoints
        that need higher OAuth scopes than our `OR.*` set). The SDK is
        kept for typed services that DO use the same OData surface, like
        `sdk.assets.*` and `sdk.tasks.*`, but most network calls in this
        wrapper go through `_http` directly.
        """
        token = ensure_fresh_token(write_dotenv_path=self.dotenv_path)
        os.environ["UIPATH_ACCESS_TOKEN"] = token.access_token
        if self._sdk is None:
            from uipath.platform import UiPath
            self._sdk = UiPath()
        return self._sdk

    @property
    def _http(self) -> httpx.Client:
        """Bearer-authenticated httpx client rooted at UIPATH_URL.

        This is the path through to OData/Maestro/Tasks endpoints that
        works with our OR.* scope set (verified by the F2 live probe
        HEAD /odata/Folders → 200). One client per folder_context call;
        caller is responsible for closing.
        """
        token = ensure_fresh_token(write_dotenv_path=self.dotenv_path)
        os.environ["UIPATH_ACCESS_TOKEN"] = token.access_token
        assert self.url is not None  # guaranteed by __init__
        return httpx.Client(
            base_url=self.url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token.access_token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    # ---------- Folders ----------

    def resolve_folder(self) -> FolderRef:
        """Return the FolderRef for self.folder. Raises if not found."""
        with self._http as client:
            r = client.get("/odata/Folders")
            r.raise_for_status()
            for f in r.json().get("value", []):
                if f.get("DisplayName") == self.folder or f.get("FullyQualifiedName") == self.folder:
                    return FolderRef(name=f["DisplayName"], id=f["Id"])
        raise RuntimeError(f"folder not found: {self.folder!r}")

    @contextmanager
    def folder_context(self) -> Iterator[FolderRef]:
        """Resolve the folder ref. Per-request callers can pass
        `X-UIPATH-OrganizationUnitId: str(ref.id)` to scope the call.
        """
        ref = self.resolve_folder()
        yield ref

    def _http_with_folder(self, ref: FolderRef) -> httpx.Client:
        """Bearer-auth client with the folder header set."""
        client = self._http
        client.headers["X-UIPATH-OrganizationUnitId"] = str(ref.id)
        return client

    # ---------- Jobs ----------

    def list_failed_jobs(self, *, since_minutes: int = 5) -> list[dict[str, Any]]:
        """Failed jobs in this folder in the last N minutes."""
        with self.folder_context() as ref, self._http_with_folder(ref) as client:
            r = client.get(
                "/odata/Jobs",
                params={
                    "$filter": f"State eq 'Faulted' and CreationTime ge {_iso_minutes_ago(since_minutes)}",
                    "$top": 100,
                },
            )
            r.raise_for_status()
            return cast(list[dict[str, Any]], r.json().get("value", []))

    def get_job(self, job_id: int) -> dict[str, Any]:
        with self.folder_context() as ref, self._http_with_folder(ref) as client:
            r = client.get(f"/odata/Jobs({job_id})")
            r.raise_for_status()
            return cast(dict[str, Any], r.json())

    # ---------- Queues ----------

    def list_failed_queue_items(self, queue_name: str, *, since_minutes: int = 60) -> list[dict[str, Any]]:
        with self.folder_context() as ref, self._http_with_folder(ref) as client:
            r = client.get(
                "/odata/QueueItems",
                params={
                    "$filter": f"QueueDefinitionName eq '{queue_name}' and Status eq 'Failed'",
                    "$top": 200,
                },
            )
            r.raise_for_status()
            return cast(list[dict[str, Any]], r.json().get("value", []))

    # ---------- Assets ----------

    def get_asset(self, name: str) -> dict[str, Any]:
        """Read an Orchestrator Asset by name (folder-scoped).

        Bypasses sdk.assets.retrieve because it routes through
        /api/FoldersNavigation which requires a higher OAuth scope than
        our OR.* set. The /odata/Assets surface works with OR.Assets.
        """
        with self.folder_context() as ref, self._http_with_folder(ref) as client:
            r = client.get("/odata/Assets", params={"$filter": f"Name eq '{name}'", "$top": 1})
            r.raise_for_status()
            items = r.json().get("value", [])
            if not items:
                raise RuntimeError(f"asset {name!r} not found in folder {self.folder!r}")
            return cast(dict[str, Any], items[0])

    def update_asset(self, name: str, value: str) -> None:
        """Set the StringValue of a Text-type Orchestrator Asset.

        UiPath OData asset update requires PUT /odata/Assets({id}) with
        the FULL asset body (not a partial PATCH — that returns 404).
        We do a read-modify-write: fetch the asset, mutate StringValue,
        PUT back. This is what `surgeon` calls to rotate GITHUB_TOKEN
        to GITHUB_TOKEN_FALLBACK on auth-failed clusters.

        sdk.assets.update is not used because it routes through the
        SetRobotAssetByRobotKey OData action which requires a robot
        execution context (a robot_key from the running job's runtime),
        which AURORA's daemon-side caller doesn't have.

        For non-Text assets (BoolValue, IntValue, CredentialPassword),
        extend this method or add a parameter.
        """
        with self.folder_context() as ref, self._http_with_folder(ref) as client:
            r = client.get("/odata/Assets", params={"$filter": f"Name eq '{name}'", "$top": 1})
            r.raise_for_status()
            items = r.json().get("value", [])
            if not items:
                raise RuntimeError(f"asset {name!r} not found in folder {self.folder!r}")
            asset = items[0]
            asset_id = asset["Id"]
            # Strip OData metadata fields that confuse the PUT.
            body = {k: v for k, v in asset.items() if not k.startswith("@")}
            body["StringValue"] = value
            pr = client.put(f"/odata/Assets({asset_id})", json=body)
            pr.raise_for_status()

    # ---------- Action Center (Tasks) ----------

    def create_form_task(
        self,
        *,
        catalog: str,
        title: str,
        priority: str,
        form_definition: dict[str, Any],
        data: dict[str, Any],
        approver_user_ids: list[int],
    ) -> dict[str, Any]:
        """Create a Form Task in Action Center, assigned to the given users."""
        with self.folder_context() as ref, self._http_with_folder(ref) as client:
            payload = {
                "Type": "FormTask",
                "Title": title,
                "Priority": priority,
                "TaskCatalogName": catalog,
                "FormDefinition": form_definition,
                "Data": data,
                "AssignedToUsers": [{"Id": uid} for uid in approver_user_ids],
            }
            r = client.post("/odata/Tasks", json=payload)
            r.raise_for_status()
            return cast(dict[str, Any], r.json())

    def get_task(self, task_id: int) -> dict[str, Any]:
        with self.folder_context() as ref, self._http_with_folder(ref) as client:
            r = client.get(f"/odata/Tasks({task_id})")
            r.raise_for_status()
            return cast(dict[str, Any], r.json())

    # ---------- Maestro instance management ----------

    def pause_maestro_instance(self, instance_id: str) -> None:
        with self.folder_context() as ref, self._http_with_folder(ref) as client:
            r = client.post(f"/maestro_/api/instances/{instance_id}/pause")
            r.raise_for_status()

    def resume_maestro_instance(self, instance_id: str) -> None:
        with self.folder_context() as ref, self._http_with_folder(ref) as client:
            r = client.post(f"/maestro_/api/instances/{instance_id}/resume")
            r.raise_for_status()

    def list_maestro_instances(
        self, *, process: str | None = None, state: str | None = None
    ) -> list[dict[str, Any]]:
        with self.folder_context() as ref, self._http_with_folder(ref) as client:
            params: dict[str, str] = {}
            if process:
                params["process"] = process
            if state:
                params["state"] = state
            r = client.get("/maestro_/api/instances", params=params)
            r.raise_for_status()
            return cast(list[dict[str, Any]], r.json().get("value", []))

    # ---------- Users (for HITL approver resolution) ----------

    def find_user_id(self, email: str) -> int | None:
        with self._http as client:
            r = client.get("/odata/Users", params={"$filter": f"EmailAddress eq '{email}'"})
            r.raise_for_status()
            users = r.json().get("value", [])
            return users[0]["Id"] if users else None

    # ---------- Maestro publish (reverse-engineered Studio Web API) ----------

    def publish_maestro_project(
        self,
        *,
        project_dir: Path,
        version_bump: str = "patch",
        fixture_path: Path | None = None,
    ) -> dict[str, Any]:
        """Publish a Maestro project via the reverse-engineered Studio Web HTTP API.

        Reads the captured fixture to learn the URL path and request shape,
        then replays it with the live OAuth bearer and folder context.
        Retries on3x on5xx per R.E.02; surfaces=4xx per R.E.03.
        """
        fixture = fixture_path or PUBLISH_FIXTURE_PATH
        access_token = os.environ.get("UIPATH_ACCESS_TOKEN", "")
        folder_ref = self.resolve_folder()
        project_key = project_dir.name

        version = _derive_next_version(project_dir, version_bump)
        req_spec = _build_publish_request(
            fixture_path=fixture,
            access_token=access_token,
            folder_id=folder_ref.id,
            project_key=project_key,
            version=version,
            version_bump=version_bump,
        )

        base_url = str(self.url).rstrip("/")
        if base_url.endswith("/orchestrator_"):
            base_url = base_url[: -len("/orchestrator_")]
        full_url = f"{base_url}{req_spec['url_path']}"

        logger.info("publishing maestro project: %s", project_dir)
        last_exc: Exception | None = None
        for attempt in range(PUBLISH_MAX_RETRIES):
            try:
                r = httpx.post(
                    full_url,
                    headers=req_spec["headers"],
                    json=req_spec["body"],
                    timeout=60,
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning("publish attempt %d network error: %s", attempt + 1, exc)
                continue

            if r.status_code >= 500:
                last_exc = RuntimeError(f"HTTP {r.status_code} from publish endpoint")
                logger.warning("publish attempt %d got %d", attempt + 1, r.status_code)
                if attempt < PUBLISH_MAX_RETRIES - 1:
                    import time
                    time.sleep(PUBLISH_RETRY_BASE_DELAY * (2 ** attempt))
                continue

            if r.status_code >= 400:
                raise BusinessError(
                    f"HTTP {r.status_code} from publish endpoint: {r.text[:200]}"
                )

            return _parse_publish_response(r.json())

        raise last_exc or RuntimeError("publish failed after retries")

    # ---------- uipath CLI shellouts ----------

    def uipath_cli(self, *args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Invoke `uipath` CLI with the live access token in the environment.

        `uipath` reads UIPATH_ACCESS_TOKEN from env. We refresh before invoking so
        long-running daemons survive token expiry without re-authing.

        Method name is `uipath_cli` (not `uipath`) to avoid shadowing the
        imported `uipath` Python module at call sites.
        """
        ensure_fresh_token(write_dotenv_path=self.dotenv_path)
        cmd = ["uipath", *args]
        logger.info("running: %s", shlex.join(cmd))
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            check=check,
            text=True,
            capture_output=True,
            env=os.environ.copy(),
        )

    def publish(self, project_dir: Path, *, folder: str | None = None) -> str:
        """Pack and publish a project. Returns the package version published."""
        self.uipath_cli("pack", cwd=project_dir)
        args = ["publish"]
        if folder:
            args.extend(["--folder", folder])
        result = self.uipath_cli(*args, cwd=project_dir)
        return result.stdout.strip()


def _iso_minutes_ago(n: int) -> str:
    from datetime import datetime, timedelta
    return (datetime.now(UTC) - timedelta(minutes=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


class BusinessError(RuntimeError):
    """Non-retryable business-logic error (4xx from UiPath APIs)."""


def _build_publish_request(
    *,
    fixture_path: Path,
    access_token: str,
    folder_id: int,
    project_key: str,
    version: str,
    version_bump: str,
) -> dict[str, Any]:
    """Pure helper: read the captured fixture and build the request spec.

    Returns a dict with keys ``method``, ``url_path``, ``headers``, ``body``.
    No I/O beyond reading the fixture file.
    """
    if not fixture_path.exists():
        raise FileNotFoundError(f"publish fixture not found: {fixture_path}")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    template_headers: dict[str, str] = fixture.get("headers", {})
    template_body: dict[str, Any] = fixture.get("body", {})

    headers: dict[str, str] = {}
    for key, value in template_headers.items():
        if "{{UIPATH_ACCESS_TOKEN}}" in value:
            headers[key] = value.replace("{{UIPATH_ACCESS_TOKEN}}", access_token)
        elif "{{folder_id}}" in value:
            headers[key] = value.replace("{{folder_id}}", str(folder_id))
        else:
            headers[key] = value

    body = dict(template_body)
    body["projectKey"] = project_key
    body["version"] = version
    body["versionBump"] = version_bump

    return {
        "method": fixture.get("method", "POST"),
        "url_path": fixture.get("url_path", "/studio_/api/publish"),
        "headers": headers,
        "body": body,
    }


def _parse_publish_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Pure helper: extract the relevant fields from a publish response."""
    return {
        "version": payload.get("version", "unknown"),
        "status": payload.get("status", "Published"),
        "projectKey": payload.get("projectKey", ""),
        "packageId": payload.get("packageId", ""),
    }


def _derive_next_version(project_dir: Path, version_bump: str) -> str:
    """Derive the next version string from the project's project.json or default."""
    project_json = project_dir / "project.json"
    if project_json.exists():
        try:
            data = json.loads(project_json.read_text(encoding="utf-8"))
            current = data.get("version", "1.0.0")
            return _bump_version(current, version_bump)
        except (json.JSONDecodeError, KeyError):
            pass
    return "1.0.0"


def _bump_version(current: str, version_bump: str) -> str:
    """Bump a semver string by the given bump type (major/minor/patch)."""
    import re
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", current)
    if not m:
        return current
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if version_bump == "major":
        return f"{major + 1}.0.0"
    if version_bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"
