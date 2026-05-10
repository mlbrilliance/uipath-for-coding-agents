"""Unit tests for aurora.replay — sandbox-folder twin replay.

Covers the pure comparison helpers, the Pydantic result shape, and verifies
the MCP server's `aurora_replay_instance` tool dispatches into the real
implementation (not the v0.1 stub).
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest
from aurora import replay
from aurora.mcp import server as mcp_server
from pydantic import ValidationError

# ---------- _compare_paths ----------


def test_compare_paths_same_returns_true() -> None:
    original = [{"step": "Start"}, {"step": "Gateway"}, {"step": "End"}]
    sandbox = [{"step": "Start"}, {"step": "Gateway"}, {"step": "End"}]
    same, divergence_step = replay._compare_paths(original, sandbox)
    assert same is True
    assert divergence_step is None


def test_compare_paths_diverged_returns_false_with_step() -> None:
    original = [{"step": "Start"}, {"step": "VulnLookup"}, {"step": "End"}]
    sandbox = [{"step": "Start"}, {"step": "MaintainerHealth"}, {"step": "End"}]
    same, divergence_step = replay._compare_paths(original, sandbox)
    assert same is False
    assert divergence_step == "VulnLookup"


# ---------- _compare_vars ----------


def test_compare_vars_at_gateways_match() -> None:
    original = [
        {"step": "Start", "kind": "start", "vars": {}},
        {"step": "G1", "kind": "gateway", "vars": {"severity": "high", "repo": "acme/x"}},
        {"step": "End", "kind": "end", "vars": {"result": "ok"}},
    ]
    sandbox = [
        {"step": "Start", "kind": "start", "vars": {}},
        {"step": "G1", "kind": "gateway", "vars": {"severity": "high", "repo": "acme/x"}},
        {"step": "End", "kind": "end", "vars": {"result": "ok"}},
    ]
    assert replay._compare_vars(original, sandbox) is True


def test_compare_vars_at_gateways_mismatch() -> None:
    original = [
        {"step": "G1", "kind": "gateway", "vars": {"severity": "high"}},
    ]
    sandbox = [
        {"step": "G1", "kind": "gateway", "vars": {"severity": "low"}},
    ]
    assert replay._compare_vars(original, sandbox) is False


# ---------- _compare_end_events ----------


def test_compare_end_events_match() -> None:
    original = [{"step": "End", "kind": "end", "name": "Insights emit"}]
    sandbox = [{"step": "End", "kind": "end", "name": "Insights emit"}]
    assert replay._compare_end_events(original, sandbox) is True


def test_compare_end_events_mismatch() -> None:
    original = [{"step": "End", "kind": "end", "name": "Insights emit"}]
    sandbox = [{"step": "Faulted", "kind": "end", "name": "Faulted"}]
    assert replay._compare_end_events(original, sandbox) is False


# ---------- ReplayResult Pydantic shape ----------


def test_replay_result_pydantic_shape() -> None:
    result = replay.ReplayResult(
        instance_id="orig-1",
        sandbox_instance_id="sb-1",
        same_path=True,
        same_end_event=True,
        same_vars_at_each_gateway=True,
        divergence_step=None,
        notes="all good",
    )
    assert result.instance_id == "orig-1"
    assert result.divergence_step is None

    # Missing required fields should fail validation.
    with pytest.raises(ValidationError):
        replay.ReplayResult(  # type: ignore[call-arg]
            instance_id="orig-1",
            same_path=True,
        )


# ---------- MCP wiring ----------


def test_mcp_aurora_replay_instance_returns_real_data() -> None:
    """The MCP dispatch must call replay_instance and return its data, not the stub."""
    fake = replay.ReplayResult(
        instance_id="abc-123",
        sandbox_instance_id="sb-abc-123",
        same_path=True,
        same_end_event=True,
        same_vars_at_each_gateway=True,
        divergence_step=None,
        notes="replay matched original",
    )
    with patch.object(replay, "replay_instance", return_value=fake) as m:
        out: Any = asyncio.run(
            mcp_server._dispatch("aurora_replay_instance", {"instance_id": "abc-123"})
        )

    assert m.called
    assert "stub" not in out, f"MCP still returning stub payload: {out!r}"
    assert out["instance_id"] == "abc-123"
    assert out["sandbox_instance_id"] == "sb-abc-123"
    assert out["same_path"] is True
    assert out["same_end_event"] is True
