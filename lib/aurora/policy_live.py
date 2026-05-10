"""Live probes for `aurora policy validate --live`.

Extends `--strict` with three independent network-level checks:

    1. Orchestrator reachability — HEAD `${UIPATH_URL}/odata/Folders`
       with the bearer token. Catches stale/wrong UIPATH_ACCESS_TOKEN,
       wrong scopes, and tenant-down conditions.
    2. GitHub reachability — HEAD `https://api.github.com/repos/{org}`
       with the GITHUB_TOKEN bearer. Catches typos in GITHUB_ORG, dead
       PATs, and network egress problems.
    3. Action Center catalog — GET CatalogIdentity for
       `${UIPATH_ACTION_CATALOG}`. Catalog must pre-exist or runtime
       error 2451 fires when Concierge first creates a Form Task.

All probes run independently; one failure does not short-circuit the
others. Aggregated `LiveProbeResult` carries each probe's status plus
a flat `failures` list of human-readable strings.

This module is unit-tested via `tests/unit/test_policy_live.py`. The
integration test (`tests/integration/test_policy_live.py`) exercises
the same code against a real tenant when `UIPATH_INTEGRATION=1`.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Final

import httpx

logger = logging.getLogger(__name__)

ORCH_PROBE_TIMEOUT: Final[float] = 5.0
GITHUB_PROBE_TIMEOUT: Final[float] = 5.0
CATALOG_PROBE_TIMEOUT: Final[float] = 5.0


@dataclass
class LiveProbeResult:
    """Per-probe status + flat failure list."""

    orchestrator_ok: bool = False
    github_ok: bool = False
    action_catalog_ok: bool = False
    failures: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return self.orchestrator_ok and self.github_ok and self.action_catalog_ok


def _require_env(*names: str) -> tuple[str | None, list[str]]:
    """Return (joined-comma value or None) and a list of any missing names.

    We don't raise — we let the caller surface missing-env-var failures
    in the same channel as network failures so the operator gets one
    pass through the punch list.
    """
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        return None, missing
    return ",".join(os.environ[n] for n in names), []


def _probe_orchestrator(client: httpx.Client) -> tuple[bool, list[str]]:
    url = os.environ.get("UIPATH_URL")
    token = os.environ.get("UIPATH_ACCESS_TOKEN")
    if not url:
        return False, ["UIPATH_URL is missing / not set in env"]
    if not token:
        return False, ["UIPATH_ACCESS_TOKEN is missing / not set in env"]
    base = url.rstrip("/")
    try:
        resp = client.head(
            f"{base}/odata/Folders",
            headers={"Authorization": f"Bearer {token}"},
            timeout=ORCH_PROBE_TIMEOUT,
        )
    except httpx.HTTPError as e:
        logger.exception("orchestrator probe: network error")
        return False, [f"orchestrator probe: network error ({e!s})"]
    if 200 <= resp.status_code < 300:
        return True, []
    return False, [f"orchestrator probe: HTTP {resp.status_code}"]


def _probe_github(client: httpx.Client) -> tuple[bool, list[str]]:
    """Verify GITHUB_ORG resolves to a real GitHub user or org.

    Uses `/users/{name}` rather than `/repos/{name}` because the latter
    needs `{owner}/{repo}` and 404s for an org-only check. `/users/`
    works for both users AND orgs (GitHub's API treats them as the
    same resource type), so this single probe covers both.
    """
    org = os.environ.get("GITHUB_ORG")
    token = os.environ.get("GITHUB_TOKEN")
    if not org:
        return False, ["GITHUB_ORG is missing / not set in env"]
    if not token:
        return False, ["GITHUB_TOKEN is missing / not set in env"]
    try:
        resp = client.head(
            f"https://api.github.com/users/{org}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=GITHUB_PROBE_TIMEOUT,
        )
    except httpx.HTTPError as e:
        logger.exception("github probe: network error")
        return False, [f"github probe: network error ({e!s})"]
    if 200 <= resp.status_code < 300:
        return True, []
    return False, [f"github probe: HTTP {resp.status_code} for /users/{org}"]


def _probe_action_catalog(client: httpx.Client) -> tuple[bool, list[str]]:
    url = os.environ.get("UIPATH_URL")
    token = os.environ.get("UIPATH_ACCESS_TOKEN")
    folder = os.environ.get("UIPATH_FOLDER")
    catalog = os.environ.get("UIPATH_ACTION_CATALOG")
    missing = [
        n for n, v in {
            "UIPATH_URL": url,
            "UIPATH_ACCESS_TOKEN": token,
            "UIPATH_FOLDER": folder,
            "UIPATH_ACTION_CATALOG": catalog,
        }.items() if not v
    ]
    if missing:
        return False, [f"action-catalog probe: missing env: {', '.join(missing)}"]
    # `missing` check above guarantees all four are non-None; assert for mypy.
    assert url is not None and token is not None and folder is not None and catalog is not None
    base = url.rstrip("/")

    # `X-UIPATH-OrganizationUnitId` requires an integer folder ID, not a name.
    # Resolve the folder name → id once via /odata/Folders, then use that.
    try:
        f_resp = client.get(
            f"{base}/odata/Folders",
            headers={"Authorization": f"Bearer {token}"},
            timeout=CATALOG_PROBE_TIMEOUT,
        )
        f_resp.raise_for_status()
        folders = f_resp.json().get("value", [])
        folder_id_match = next(
            (f for f in folders
             if f.get("DisplayName") == folder or f.get("FullyQualifiedName") == folder),
            None,
        )
        if folder_id_match is None:
            return False, [
                f"action-catalog probe: folder {folder!r} not found in /odata/Folders"
            ]
        folder_id = str(folder_id_match["Id"])
    except (httpx.HTTPError, ValueError, KeyError) as e:
        logger.exception("action-catalog probe: folder resolution failed")
        return False, [f"action-catalog probe: folder resolution failed ({e!s})"]

    try:
        # Use the OData TaskCatalogs endpoint — verified live.
        resp = client.get(
            f"{base}/odata/TaskCatalogs",
            params={"$filter": f"Name eq '{catalog}'"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-UIPATH-OrganizationUnitId": folder_id,
            },
            timeout=CATALOG_PROBE_TIMEOUT,
        )
    except httpx.HTTPError as e:
        logger.exception("action-catalog probe: network error")
        return False, [f"action-catalog probe: network error ({e!s})"]
    if 200 <= resp.status_code < 300:
        try:
            data = resp.json()
        except ValueError:
            return False, [
                f"action-catalog probe: HTTP {resp.status_code} but response not JSON"
            ]
        # OData returns {"@odata.count": N, "value": [...]}.
        items = data.get("value", [])
        if items and any(item.get("Name") == catalog for item in items):
            return True, []
        return False, [
            f"action-catalog probe: catalog {catalog!r} not found in TaskCatalogs "
            f"(runtime error 2451 will fire if Concierge tries to use it)"
        ]
    return False, [f"action-catalog probe: HTTP {resp.status_code} on /odata/TaskCatalogs"]


def run_live_probes() -> LiveProbeResult:
    """Execute the three live probes, aggregate results."""
    result = LiveProbeResult()
    with httpx.Client() as client:
        result.orchestrator_ok, fails = _probe_orchestrator(client)
        result.failures.extend(fails)
        result.github_ok, fails = _probe_github(client)
        result.failures.extend(fails)
        result.action_catalog_ok, fails = _probe_action_catalog(client)
        result.failures.extend(fails)
    return result
