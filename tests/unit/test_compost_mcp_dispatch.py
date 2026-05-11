"""Independent smoke test for `aurora_compost_dry_run` MCP tool dispatch.

The compost-dry-run path is registered in `lib/aurora/mcp/server.py`'s
`list_tools()` and dispatched in `_dispatch()`. Other compost tests cover the
underlying `propose_skill_pr` function (`tests/unit/test_compost.py`), but
nothing previously exercised the MCP-tool wrapper end-to-end. This test
asserts that dispatching `aurora_compost_dry_run` returns a well-formed
response shape with a `candidates` list, even when the learnings file is
absent or sparse.

T-B4 acceptance: the MCP tool's wire-through is independently verified.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from aurora.mcp import server as mcp_server


@pytest.fixture
def aurora_home_with_no_learnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """AURORA_HOME points at an empty dir — exercises the empty-learnings path."""
    (tmp_path / "learnings").mkdir()
    monkeypatch.setenv("AURORA_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def aurora_home_with_sparse_learnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """AURORA_HOME with two learnings (below the ≥3 occurrences threshold)."""
    learnings = tmp_path / "learnings"
    learnings.mkdir()
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    jsonl = learnings / f"{today}.jsonl"
    jsonl.write_text("\n".join(
        json.dumps({
            "ts": "2026-05-11T01:23:45Z",
            "agent": "diagnostician",
            "project_id": f"P-{i}",
            "kind": "auth-failed",
            "summary": "token expired",
        })
        for i in range(2)
    ) + "\n")
    monkeypatch.setenv("AURORA_HOME", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_dispatch_returns_candidates_shape(aurora_home_with_no_learnings: Path) -> None:
    """The dispatch path returns a dict with `since_days` and `candidates`
    keys; candidates is a list (possibly empty)."""
    result = await mcp_server._dispatch("aurora_compost_dry_run", {"since_days": 1})
    assert isinstance(result, dict)
    assert result.get("since_days") == 1
    assert "candidates" in result
    assert isinstance(result["candidates"], list)


@pytest.mark.asyncio
async def test_dispatch_below_occurrence_threshold_returns_empty(
    aurora_home_with_sparse_learnings: Path,
) -> None:
    """≥ 3 occurrences across ≥ 2 projects required — 2 occurrences should
    not pass the gate, so candidates is empty."""
    result = await mcp_server._dispatch("aurora_compost_dry_run", {"since_days": 1})
    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_unknown_tool_name_raises(aurora_home_with_no_learnings: Path) -> None:
    """Sanity check: unknown tool names raise ValueError — protects the
    dispatcher from silently masking integration drift."""
    with pytest.raises(ValueError, match="unknown tool"):
        await mcp_server._dispatch("aurora_definitely_not_a_real_tool", {})
