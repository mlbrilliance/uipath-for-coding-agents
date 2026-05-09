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

import logging
import os
import shlex
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

import httpx

from aurora.auth import ensure_fresh_token

logger = logging.getLogger(__name__)


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
        url: Optional[str] = None,
        folder: Optional[str] = None,
        dotenv_path: Optional[Path] = None,
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
        if the cached one is stale."""
        token = ensure_fresh_token(write_dotenv_path=self.dotenv_path)
        # Mutate environment so the SDK picks it up. (Some uipath versions
        # accept access_token as a constructor param; we use env for portability.)
        os.environ["UIPATH_ACCESS_TOKEN"] = token.access_token
        if self._sdk is None:
            from uipath.platform import UiPath  # type: ignore
            self._sdk = UiPath()
        return self._sdk

    # ---------- Folders ----------

    def resolve_folder(self) -> FolderRef:
        """Return the FolderRef for self.folder. Raises if not found."""
        for f in self.sdk.api_client.get("/odata/Folders").json().get("value", []):
            if f.get("DisplayName") == self.folder or f.get("FullyQualifiedName") == self.folder:
                return FolderRef(name=f["DisplayName"], id=f["Id"])
        raise RuntimeError(f"folder not found: {self.folder!r}")

    @contextmanager
    def folder_context(self) -> Iterator[FolderRef]:
        """Set X-UIPATH-OrganizationUnitId header for the duration of the block."""
        ref = self.resolve_folder()
        # Many SDK calls accept folder via header — set on the client.
        self.sdk.api_client.headers["X-UIPATH-OrganizationUnitId"] = str(ref.id)
        try:
            yield ref
        finally:
            self.sdk.api_client.headers.pop("X-UIPATH-OrganizationUnitId", None)

    # ---------- Jobs ----------

    def list_failed_jobs(self, *, since_minutes: int = 5) -> list[dict]:
        """Failed jobs in this folder in the last N minutes."""
        with self.folder_context():
            params = {
                "$filter": f"State eq 'Faulted' and CreationTime ge {_iso_minutes_ago(since_minutes)}",
                "$top": 100,
            }
            r = self.sdk.api_client.get("/odata/Jobs", params=params)
            return r.json().get("value", [])

    def get_job(self, job_id: int) -> dict:
        with self.folder_context():
            return self.sdk.api_client.get(f"/odata/Jobs({job_id})").json()

    # ---------- Queues ----------

    def list_failed_queue_items(self, queue_name: str, *, since_minutes: int = 60) -> list[dict]:
        with self.folder_context():
            params = {
                "$filter": f"QueueDefinitionName eq '{queue_name}' and Status eq 'Failed'",
                "$top": 200,
            }
            r = self.sdk.api_client.get("/odata/QueueItems", params=params)
            return r.json().get("value", [])

    # ---------- Assets ----------

    def get_asset(self, name: str) -> dict:
        with self.folder_context():
            return self.sdk.assets.retrieve(name=name)  # type: ignore[no-any-return]

    def update_asset(self, name: str, value: str) -> None:
        with self.folder_context():
            self.sdk.assets.update(name=name, value=value)

    # ---------- Action Center (Tasks) ----------

    def create_form_task(
        self,
        *,
        catalog: str,
        title: str,
        priority: str,
        form_definition: dict,
        data: dict,
        approver_user_ids: list[int],
    ) -> dict:
        """Create a Form Task in Action Center, assigned to the given users."""
        with self.folder_context():
            # Form Tasks live under /odata/Tasks with Type=FormTask
            payload = {
                "Type": "FormTask",
                "Title": title,
                "Priority": priority,
                "TaskCatalogName": catalog,
                "FormDefinition": form_definition,
                "Data": data,
                "AssignedToUsers": [{"Id": uid} for uid in approver_user_ids],
            }
            r = self.sdk.api_client.post("/odata/Tasks", json=payload)
            r.raise_for_status()
            return r.json()

    def get_task(self, task_id: int) -> dict:
        with self.folder_context():
            r = self.sdk.api_client.get(f"/odata/Tasks({task_id})")
            return r.json()

    # ---------- Maestro instance management ----------

    def pause_maestro_instance(self, instance_id: str) -> None:
        with self.folder_context():
            r = self.sdk.api_client.post(
                f"/maestro_/api/instances/{instance_id}/pause"
            )
            r.raise_for_status()

    def resume_maestro_instance(self, instance_id: str) -> None:
        with self.folder_context():
            r = self.sdk.api_client.post(
                f"/maestro_/api/instances/{instance_id}/resume"
            )
            r.raise_for_status()

    def list_maestro_instances(
        self, *, process: Optional[str] = None, state: Optional[str] = None
    ) -> list[dict]:
        with self.folder_context():
            params: dict[str, str] = {}
            if process:
                params["process"] = process
            if state:
                params["state"] = state
            r = self.sdk.api_client.get("/maestro_/api/instances", params=params)
            return r.json().get("value", [])

    # ---------- Users (for HITL approver resolution) ----------

    def find_user_id(self, email: str) -> Optional[int]:
        r = self.sdk.api_client.get("/odata/Users", params={"$filter": f"EmailAddress eq '{email}'"})
        users = r.json().get("value", [])
        return users[0]["Id"] if users else None

    # ---------- uipath CLI shellouts ----------

    def uipath_cli(self, *args: str, cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
        """Invoke `uipath` CLI with the live access token in the environment.

        `uipath` reads UIPATH_ACCESS_TOKEN from env. We refresh before invoking so
        long-running daemons survive token expiry without re-authing.

        Method name is `uipath_cli` (not `uipath`) to avoid shadowing the
        imported `uipath` Python module at call sites.
        """
        ensure_fresh_token(write_dotenv_path=self.dotenv_path)
        cmd = ["uipath", *args]
        logger.info("running: %s", shlex.join(cmd))
        return subprocess.run(  # noqa: S603
            cmd,
            cwd=str(cwd) if cwd else None,
            check=check,
            text=True,
            capture_output=True,
            env=os.environ.copy(),
        )

    def publish(self, project_dir: Path, *, folder: Optional[str] = None) -> str:
        """Pack and publish a project. Returns the package version published."""
        self.uipath_cli("pack", cwd=project_dir)
        args = ["publish"]
        if folder:
            args.extend(["--folder", folder])
        result = self.uipath_cli(*args, cwd=project_dir)
        return result.stdout.strip()


def _iso_minutes_ago(n: int) -> str:
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(minutes=n)).strftime("%Y-%m-%dT%H:%M:%SZ")
