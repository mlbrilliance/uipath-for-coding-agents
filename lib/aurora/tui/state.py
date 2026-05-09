"""Live-state collector for the `aurora status` TUI.

Reads operational artifacts under ``${AURORA_HOME}`` (events.jsonl, gate
files, per-agent heartbeat files). This is the *operational* event stream,
not the AURORA memory tier — R.SW.04 (memory access via aurora-recall only)
applies to ``.aurora/projects/`` / ``.aurora/org/`` / ``.aurora/learnings/``,
not to the live ``events.jsonl`` Sentry writes for Diagnostician to consume.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# Three fleets, 19 agents — keep in sync with ``agents/*.md``.
AGENT_FLEETS: dict[str, list[str]] = {
    "discovery": ["scout", "curator", "analyst", "interviewer", "strategist"],
    "build": [
        "architect",
        "cartographer",
        "forger-rpa",
        "forger-coded",
        "forger-agent",
        "forger-maestro",
        "reviewer",
        "tester",
    ],
    "operate": ["sentry", "diagnostician", "surgeon", "auditor", "concierge"],
    "meta": ["conductor"],
}

# Claude tiers tracked by the budget meter (mirrors ``policy.yaml::routing.defaults``).
CLAUDE_TIERS: tuple[str, ...] = ("opus", "sonnet", "haiku")

EVENTS_TAIL_LINES = 50


class LiveState(BaseModel):
    """Snapshot of swarm state for the TUI."""

    events: list[dict[str, Any]] = Field(default_factory=list)
    agents: list[dict[str, Any]] = Field(default_factory=list)
    gates: list[dict[str, Any]] = Field(default_factory=list)
    budget: dict[str, dict[str, float]] = Field(default_factory=dict)


def _aurora_home(override: Path | None = None) -> Path:
    if override is not None:
        return override
    return Path(os.environ.get("AURORA_HOME", "/opt/aurora"))


def _tail_jsonl(path: Path, n: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for raw in lines[-n:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def _load_agents(home: Path) -> list[dict[str, Any]]:
    """Walk per-agent heartbeat files at ``${AURORA_HOME}/agents/<name>.json``.

    Tolerate missing files: an unknown agent is reported as ``state=idle``,
    ``last_action_ts=None``.
    """
    agents_dir = home / "agents"
    out: list[dict[str, Any]] = []
    for fleet, names in AGENT_FLEETS.items():
        for name in names:
            entry: dict[str, Any] = {
                "name": name,
                "fleet": fleet,
                "last_action_ts": None,
                "current_state": "idle",
            }
            f = agents_dir / f"{name}.json"
            if f.exists():
                try:
                    blob = json.loads(f.read_text(encoding="utf-8"))
                    entry["last_action_ts"] = blob.get("last_action_ts")
                    entry["current_state"] = blob.get("current_state", "idle")
                except (OSError, json.JSONDecodeError):
                    pass
            out.append(entry)
    return out


def _load_gates(home: Path) -> list[dict[str, Any]]:
    """Read pending HITL gates from ``${AURORA_HOME}/gates/*.json``."""
    gates_dir = home / "gates"
    if not gates_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for f in sorted(gates_dir.glob("*.json")):
        try:
            blob = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if blob.get("status", "pending") != "pending":
            continue
        out.append(blob)
    return out


def _load_budget(home: Path) -> dict[str, dict[str, float]]:
    """Read today's spend per Claude tier from ``${AURORA_HOME}/budget/<YYYY-MM-DD>.json``.

    Schema: ``{"<tier>": {"spent": float, "ceiling": float}, ...}``.
    Always returns an entry for each of ``CLAUDE_TIERS`` (zero if missing) so the
    meter can render a stable layout.
    """
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    f = home / "budget" / f"{today}.json"
    raw: dict[str, Any] = {}
    if f.exists():
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
    out: dict[str, dict[str, float]] = {}
    for tier in CLAUDE_TIERS:
        entry = raw.get(tier) or {}
        out[tier] = {
            "spent": float(entry.get("spent", 0.0)),
            "ceiling": float(entry.get("ceiling", 0.0)),
        }
    return out


def load_state(aurora_home: Path | None = None) -> LiveState:
    """Build a ``LiveState`` snapshot. Tolerates missing files (returns defaults)."""
    home = _aurora_home(aurora_home)
    return LiveState(
        events=_tail_jsonl(home / "events.jsonl", EVENTS_TAIL_LINES),
        agents=_load_agents(home),
        gates=_load_gates(home),
        budget=_load_budget(home),
    )
