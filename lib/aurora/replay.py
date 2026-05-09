"""Sandbox-folder twin replay for faulted Maestro instances.

Replay a faulted Maestro instance in a sandbox folder using its original
input data, to isolate whether the root cause is in the bot, environment,
or external dependency. The "shadow twin" pattern from AURORA's design.

Used by Diagnostician (and surfaced via the MCP tool
`aurora_replay_instance`) on faults whose fingerprint cluster has low
confidence, where we want to know whether the same inputs produce the
same failure in a clean folder.

The flow:

    1. Pull the original instance (inputs, package version, event log).
    2. Ensure the sandbox folder exists.
    3. Ensure the same package+version is deployed in the sandbox.
    4. Start a new instance in the sandbox folder with the same inputs.
    5. Wait for completion.
    6. Compare path / vars at each gateway / end event.

Comparison helpers are pure so tests can drive them with synthetic dicts
without touching the SDK. Per R.K.01.
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

import structlog
from pydantic import BaseModel

from aurora.uipath_client import UiPathClient


logger = structlog.get_logger(__name__)


# How long to wait for the sandbox instance to finish before giving up.
DEFAULT_AWAIT_SECONDS = 30 * 60
DEFAULT_POLL_SECONDS = 10
TERMINAL_STATES = frozenset(
    {"Completed", "Faulted", "Cancelled", "Canceled", "Failed", "Succeeded"}
)


class ReplayResult(BaseModel):
    """Outcome of a sandbox-folder replay vs the original instance."""

    instance_id: str
    sandbox_instance_id: str
    same_path: bool
    same_end_event: bool
    same_vars_at_each_gateway: bool
    divergence_step: Optional[str] = None
    notes: str


# ---------- Pure comparison helpers (R.K.01) ----------


def _compare_paths(
    original_log: list[dict[str, Any]],
    sandbox_log: list[dict[str, Any]],
) -> tuple[bool, Optional[str]]:
    """Return (same, divergence_step). Compares the ordered list of `step`s.

    Divergence step is the first step in the *original* log that doesn't match
    the sandbox log (or the first step that exists only in one log).
    """
    for orig, sand in zip(original_log, sandbox_log):
        if orig.get("step") != sand.get("step"):
            return False, str(orig.get("step")) if orig.get("step") is not None else None
    if len(original_log) != len(sandbox_log):
        # Whichever ran longer — the first extra step is the divergence.
        longer = original_log if len(original_log) > len(sandbox_log) else sandbox_log
        idx = min(len(original_log), len(sandbox_log))
        if idx < len(longer):
            return False, str(longer[idx].get("step"))
        return False, None
    return True, None


def _compare_vars(
    original_log: list[dict[str, Any]],
    sandbox_log: list[dict[str, Any]],
) -> bool:
    """Are the variable snapshots at each gateway equal?

    Only `kind == "gateway"` events participate; everything else is ignored.
    Vars compared by exact dict equality.
    """
    orig_gw = [e for e in original_log if e.get("kind") == "gateway"]
    sand_gw = [e for e in sandbox_log if e.get("kind") == "gateway"]
    if len(orig_gw) != len(sand_gw):
        return False
    for o, s in zip(orig_gw, sand_gw):
        if o.get("vars") != s.get("vars"):
            return False
    return True


def _compare_end_events(
    original_log: list[dict[str, Any]],
    sandbox_log: list[dict[str, Any]],
) -> bool:
    """Did both instances finish at the same end event?"""
    orig_end = next((e for e in reversed(original_log) if e.get("kind") == "end"), None)
    sand_end = next((e for e in reversed(sandbox_log) if e.get("kind") == "end"), None)
    if orig_end is None or sand_end is None:
        return orig_end is None and sand_end is None
    return orig_end.get("name") == sand_end.get("name") and orig_end.get("step") == sand_end.get("step")


# ---------- SDK-touching helpers ----------


def _get_instance_details(client: UiPathClient, instance_id: str) -> dict[str, Any]:
    """Fetch original instance metadata: inputs, package, version."""
    try:
        with client.folder_context():
            r = client.sdk.api_client.get(f"/maestro_/api/instances/{instance_id}")
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]
    except Exception:
        logger.exception("replay.get_instance_details_failed", instance_id=instance_id)
        raise


def _get_instance_event_log(client: UiPathClient, instance_id: str) -> list[dict[str, Any]]:
    """Fetch the chronological event log for an instance."""
    try:
        with client.folder_context():
            r = client.sdk.api_client.get(f"/maestro_/api/instances/{instance_id}/events")
            r.raise_for_status()
            payload = r.json()
            if isinstance(payload, list):
                return payload
            return list(payload.get("value", []))
    except Exception:
        logger.exception("replay.get_event_log_failed", instance_id=instance_id)
        raise


def _ensure_sandbox_folder(client: UiPathClient, sandbox_folder: str) -> None:
    """Idempotent: create the sandbox folder if it doesn't already exist."""
    try:
        existing = client.sdk.api_client.get("/odata/Folders").json().get("value", [])
        for f in existing:
            if f.get("DisplayName") == sandbox_folder or f.get("FullyQualifiedName") == sandbox_folder:
                logger.debug("replay.sandbox_folder_present", folder=sandbox_folder)
                return
        logger.info("replay.creating_sandbox_folder", folder=sandbox_folder)
        r = client.sdk.api_client.post(
            "/odata/Folders",
            json={"DisplayName": sandbox_folder, "FullyQualifiedName": sandbox_folder},
        )
        r.raise_for_status()
    except Exception:
        logger.exception("replay.ensure_sandbox_folder_failed", folder=sandbox_folder)
        raise


def _ensure_package_in_sandbox(
    client: UiPathClient,
    sandbox_folder: str,
    package_name: str,
    package_version: str,
) -> None:
    """Idempotent: deploy the package+version into the sandbox folder if missing."""
    try:
        # Check existing processes in sandbox folder.
        sandbox_client = UiPathClient(url=client.url, folder=sandbox_folder, dotenv_path=client.dotenv_path)
        with sandbox_client.folder_context():
            r = sandbox_client.sdk.api_client.get(
                "/odata/Releases",
                params={"$filter": f"ProcessKey eq '{package_name}'"},
            )
            for rel in r.json().get("value", []):
                if rel.get("ProcessVersion") == package_version:
                    logger.debug(
                        "replay.package_already_in_sandbox",
                        folder=sandbox_folder,
                        package=package_name,
                        version=package_version,
                    )
                    return
            logger.info(
                "replay.deploying_package_to_sandbox",
                folder=sandbox_folder,
                package=package_name,
                version=package_version,
            )
            payload = {"ProcessKey": package_name, "ProcessVersion": package_version, "Name": package_name}
            r = sandbox_client.sdk.api_client.post("/odata/Releases", json=payload)
            r.raise_for_status()
    except Exception:
        logger.exception(
            "replay.ensure_package_failed",
            folder=sandbox_folder,
            package=package_name,
            version=package_version,
        )
        raise


def _start_sandbox_instance(
    client: UiPathClient,
    sandbox_folder: str,
    package_name: str,
    package_version: str,
    inputs: dict[str, Any],
) -> str:
    """Start a Maestro instance in the sandbox folder with the supplied inputs.

    Returns the new instance_id.
    """
    try:
        sandbox_client = UiPathClient(url=client.url, folder=sandbox_folder, dotenv_path=client.dotenv_path)
        with sandbox_client.folder_context():
            r = sandbox_client.sdk.api_client.post(
                "/maestro_/api/instances",
                json={
                    "process": package_name,
                    "version": package_version,
                    "input": inputs,
                },
            )
            r.raise_for_status()
            payload = r.json()
            instance_id = payload.get("instanceId") or payload.get("id") or payload.get("Id")
            if not instance_id:
                raise RuntimeError(f"sandbox start returned no instance id: {payload!r}")
            return str(instance_id)
    except Exception:
        logger.exception(
            "replay.start_sandbox_instance_failed",
            folder=sandbox_folder,
            package=package_name,
        )
        raise


def _await_completion(
    client: UiPathClient,
    sandbox_folder: str,
    instance_id: str,
    *,
    timeout_seconds: int = DEFAULT_AWAIT_SECONDS,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
) -> dict[str, Any]:
    """Poll the sandbox instance until it reaches a terminal state or times out."""
    deadline = time.time() + timeout_seconds
    sandbox_client = UiPathClient(url=client.url, folder=sandbox_folder, dotenv_path=client.dotenv_path)
    while True:
        try:
            with sandbox_client.folder_context():
                r = sandbox_client.sdk.api_client.get(
                    f"/maestro_/api/instances/{instance_id}"
                )
                r.raise_for_status()
                detail = r.json()
        except Exception:
            logger.exception("replay.poll_failed", instance_id=instance_id)
            raise

        state = detail.get("state") or detail.get("State") or detail.get("status")
        if state in TERMINAL_STATES:
            logger.info("replay.sandbox_completed", instance_id=instance_id, state=state)
            return detail  # type: ignore[no-any-return]

        if time.time() > deadline:
            logger.warning(
                "replay.sandbox_timeout",
                instance_id=instance_id,
                state=state,
                timeout_seconds=timeout_seconds,
            )
            return detail  # type: ignore[no-any-return]

        time.sleep(poll_seconds)


# ---------- Public entry point ----------


def replay_instance(
    instance_id: str,
    sandbox_folder: Optional[str] = None,
    *,
    client: Optional[UiPathClient] = None,
    await_seconds: int = DEFAULT_AWAIT_SECONDS,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
) -> ReplayResult:
    """Replay `instance_id` in `sandbox_folder` and return a comparison report.

    Args:
        instance_id: The original (faulted) Maestro instance to replay.
        sandbox_folder: Override the sandbox folder. Defaults to
            ``f"{UIPATH_FOLDER}-Sandbox"``.
        client: Inject a pre-built UiPathClient (for tests). Production callers
            should leave this None — replay constructs one and reuses it so
            tokens aren't re-minted across the helper functions.
        await_seconds: How long to wait for the sandbox instance to finish.
        poll_seconds: Sleep between polls.

    Returns:
        ReplayResult with same_path / same_end_event / same_vars_at_each_gateway
        plus an optional `divergence_step` and free-form `notes`.
    """
    if sandbox_folder is None:
        base_folder = os.environ.get("UIPATH_FOLDER")
        if not base_folder:
            raise RuntimeError(
                "UIPATH_FOLDER not set; pass sandbox_folder explicitly or set the env var"
            )
        sandbox_folder = f"{base_folder}-Sandbox"

    log = logger.bind(instance_id=instance_id, sandbox_folder=sandbox_folder)
    log.info("replay.start")

    client = client or UiPathClient()

    detail = _get_instance_details(client, instance_id)
    inputs = detail.get("input") or detail.get("Input") or {}
    package_name = (
        detail.get("process")
        or detail.get("Process")
        or detail.get("packageName")
        or detail.get("PackageName")
        or ""
    )
    package_version = (
        detail.get("version")
        or detail.get("Version")
        or detail.get("packageVersion")
        or detail.get("PackageVersion")
        or ""
    )
    if not package_name or not package_version:
        raise RuntimeError(
            f"original instance {instance_id} has no package name/version "
            f"(got name={package_name!r} version={package_version!r})"
        )

    original_log = _get_instance_event_log(client, instance_id)

    _ensure_sandbox_folder(client, sandbox_folder)
    _ensure_package_in_sandbox(client, sandbox_folder, package_name, package_version)

    sandbox_instance_id = _start_sandbox_instance(
        client, sandbox_folder, package_name, package_version, inputs
    )
    log = log.bind(sandbox_instance_id=sandbox_instance_id)
    log.info("replay.sandbox_started")

    _await_completion(
        client,
        sandbox_folder,
        sandbox_instance_id,
        timeout_seconds=await_seconds,
        poll_seconds=poll_seconds,
    )

    sandbox_log = _get_instance_event_log(client, sandbox_instance_id)

    same_path, divergence_step = _compare_paths(original_log, sandbox_log)
    same_vars = _compare_vars(original_log, sandbox_log)
    same_end = _compare_end_events(original_log, sandbox_log)

    notes_parts = []
    if same_path and same_end and same_vars:
        notes_parts.append("sandbox replay reproduced the original outcome — root cause is in the bot, not env")
    elif not same_path:
        notes_parts.append(f"diverged at step {divergence_step!r}")
    elif not same_end:
        notes_parts.append("paths matched but end events differ — likely environmental flake")
    elif not same_vars:
        notes_parts.append("paths matched but gateway vars differ — input drift suspected")
    notes = "; ".join(notes_parts) or "replay completed"

    result = ReplayResult(
        instance_id=instance_id,
        sandbox_instance_id=sandbox_instance_id,
        same_path=same_path,
        same_end_event=same_end,
        same_vars_at_each_gateway=same_vars,
        divergence_step=divergence_step,
        notes=notes,
    )
    log.info(
        "replay.complete",
        same_path=same_path,
        same_end_event=same_end,
        same_vars=same_vars,
    )
    return result
