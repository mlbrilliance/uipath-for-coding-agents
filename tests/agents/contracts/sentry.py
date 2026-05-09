"""Sentry event contract + offline parser shim.

Sentry's job is to translate Orchestrator state into structured events on
``events.jsonl``. The contract is the ``Event`` pydantic model below; the
shim ``parse_events_to_jsonl`` walks a recorded state snapshot and yields
events without touching the live SDK.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

EventKind = Literal[
    "job_faulted",
    "queue_idle",
    "queue_item_failed",
    "asset_missing",
    "asset_modified",
    "auth_failed",
    "robot_offline",
    "license_high",
    "maestro_instance_faulted",
]

Severity = Literal["info", "warning", "error", "critical"]

_SEVERITY_BY_KIND: dict[str, Severity] = {
    "job_faulted": "error",
    "queue_item_failed": "error",
    "auth_failed": "critical",
    "asset_missing": "warning",
    "asset_modified": "info",
    "queue_idle": "info",
    "robot_offline": "warning",
    "license_high": "warning",
    "maestro_instance_faulted": "error",
}


class Event(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: EventKind
    ts: datetime
    severity: Severity
    payload: dict[str, Any] = Field(default_factory=dict)


def parse_events_to_jsonl(state: dict[str, Any]) -> list[Event]:
    """Translate a recorded Orchestrator state snapshot into typed Events.

    The state shape mirrors what ``UiPathClient`` would surface; the SDK is
    expected to be mocked by callers — this shim never performs I/O itself.
    """
    events: list[Event] = []
    for job in state.get("faulted_jobs", []):
        events.append(_event("job_faulted", job["ended_at"], job))
    for item in state.get("failed_queue_items", []):
        events.append(_event("queue_item_failed", item["failed_at"], item))
    for queue in state.get("idle_queues", []):
        events.append(_event("queue_idle", queue["observed_at"], queue))
    for asset in state.get("missing_assets", []):
        events.append(_event("asset_missing", asset["observed_at"], asset))
    for failure in state.get("auth_failures", []):
        events.append(_event("auth_failed", failure["observed_at"], failure))
    for inst in state.get("faulted_maestro_instances", []):
        events.append(_event("maestro_instance_faulted", inst["faulted_at"], inst))
    return events


def events_to_jsonl(events: list[Event]) -> str:
    return "\n".join(e.model_dump_json() for e in events) + "\n"


def fingerprint(events: list[Event]) -> str:
    canon = [e.model_dump(mode="json") for e in events]
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _event(kind: EventKind, ts: Any, payload: dict[str, Any]) -> Event:
    return Event(kind=kind, ts=ts, severity=_SEVERITY_BY_KIND[kind], payload=payload)
