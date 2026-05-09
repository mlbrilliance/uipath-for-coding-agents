"""AURORA — Autonomous UiPath RPA Operations & Reasoning Agency.

A 15+ agent swarm that builds, tests, deploys, monitors, and self-heals
UiPath automations end-to-end. This package contains the runtime that
backs the Claude Code subagents, the Operate-fleet daemons, and the
custom MCP server.

Key entrypoints:
    aurora.cli              — `aurora` CLI (start, status, policy, recall, ...)
    aurora.conductor        — long-running orchestration loop
    aurora.sentry           — Orchestrator polling daemon
    aurora.mcp.server       — custom MCP exposing recall/fingerprint/replay/compost

Cross-cutting:
    aurora.auth             — UiPath OAuth client-credentials minting + refresh
    aurora.uipath_client    — uipath-python SDK + uipath CLI wrapper
    aurora.memory           — three-tier memory store
    aurora.fingerprint      — failure clustering
    aurora.policy           — policy.yaml loader / validator / dry-run
    aurora.recall           — scoped memory retrieval
    aurora.promote          — Action Center HITL gates
"""
from __future__ import annotations

__version__ = "0.1.0"

# Re-export the most-used surfaces so callers can `from aurora import …`
from aurora.auth import mint_token, get_cached_token, ensure_fresh_token  # noqa: E402,F401
from aurora.policy import load_policy, validate_policy, AuroraPolicy  # noqa: E402,F401
from aurora.memory import MemoryStore  # noqa: E402,F401
from aurora.fingerprint import classify_event, append_resolution  # noqa: E402,F401
from aurora.recall import recall  # noqa: E402,F401
from aurora.promote import open_gate  # noqa: E402,F401

__all__ = [
    "__version__",
    "mint_token",
    "get_cached_token",
    "ensure_fresh_token",
    "load_policy",
    "validate_policy",
    "AuroraPolicy",
    "MemoryStore",
    "classify_event",
    "append_resolution",
    "recall",
    "open_gate",
]
