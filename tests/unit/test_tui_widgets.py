"""Unit tests for the `aurora status` Textual TUI (T-B2).

Covers state loading, per-widget rendering, and a smoke test for the app shell.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from aurora.tui.app import AuroraStatusApp
from aurora.tui.state import AGENT_FLEETS, CLAUDE_TIERS, LiveState, load_state
from aurora.tui.widgets.agent_grid import AgentGrid
from aurora.tui.widgets.budget_meter import BudgetMeter
from aurora.tui.widgets.event_tail import EventTail
from aurora.tui.widgets.gates_pane import EMPTY_MESSAGE, GatesPane

# ---------- state ----------

def test_load_state_handles_missing_files(tmp_path: Path) -> None:
    state = load_state(tmp_path)
    assert isinstance(state, LiveState)
    assert state.events == []
    assert state.gates == []
    # Every agent enumerated even when no heartbeat files exist.
    expected_count = sum(len(v) for v in AGENT_FLEETS.values())
    assert len(state.agents) == expected_count == 19
    assert all(a["current_state"] == "idle" for a in state.agents)
    # Budget always has all three tiers, all zero.
    assert set(state.budget.keys()) == set(CLAUDE_TIERS)
    for tier in CLAUDE_TIERS:
        assert state.budget[tier] == {"spent": 0.0, "ceiling": 0.0}


def test_load_state_reads_events_jsonl(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        json.dumps({"ts": "2026-05-09T00:00:00Z", "kind": "job_failed", "scope": {"process": "P"}, "details": {"message": "boom"}}) + "\n"
        + json.dumps({"ts": "2026-05-09T00:00:01Z", "kind": "ok"}) + "\n"
        + "  \n"  # blank lines tolerated
        + "{not json}\n",  # corrupt lines tolerated
        encoding="utf-8",
    )
    state = load_state(tmp_path)
    assert len(state.events) == 2
    assert state.events[0]["kind"] == "job_failed"
    assert state.events[1]["kind"] == "ok"


# ---------- EventTail ----------

def test_event_tail_renders_colour_per_kind() -> None:
    tail = EventTail()
    failure = tail._format_line({"ts": "T", "kind": "job_failed", "details": {"message": "x"}})
    success = tail._format_line({"ts": "T", "kind": "job_succeeded"})
    info = tail._format_line({"ts": "T", "kind": "sentry_tick"})

    # The kind token's style is set via Text.append; inspect the styled spans.
    failure_styles = [span.style for span in failure.spans]
    success_styles = [span.style for span in success.spans]
    info_styles = [span.style for span in info.spans]

    assert any("red" in str(s) for s in failure_styles)
    assert any("green" in str(s) for s in success_styles)
    # info kinds fall back to default
    assert all("red" not in str(s) and "green" not in str(s) for s in info_styles)


# ---------- AgentGrid ----------

def test_agent_grid_renders_19_cells() -> None:
    grid = AgentGrid()
    state = LiveState(agents=load_state(Path("/tmp/__nonexistent_aurora_home__")).agents)
    grid.build_table(state)
    assert len(grid.cells) == 19
    # Spot-check a known agent appears in cell content.
    rendered = "".join(c.plain for c in grid.cells)
    for fleet in AGENT_FLEETS.values():
        for name in fleet:
            assert name in rendered


# ---------- GatesPane ----------

def test_gates_pane_empty_state() -> None:
    pane = GatesPane()
    rendered = pane.build_text(LiveState())
    assert EMPTY_MESSAGE in rendered.plain


def test_gates_pane_sorts_by_deadline() -> None:
    now = datetime(2026, 5, 9, 12, 0, tzinfo=UTC)
    state = LiveState(
        gates=[
            {"id": "G3", "kind": "prod_publish", "deadline": (now + timedelta(hours=8)).isoformat()},
            {"id": "G1", "kind": "prod_publish", "deadline": (now + timedelta(hours=1)).isoformat()},
            {"id": "G2", "kind": "prod_publish", "deadline": (now + timedelta(hours=4)).isoformat()},
        ]
    )
    pane = GatesPane()
    rendered = pane.build_text(state, now=now).plain
    pos1, pos2, pos3 = rendered.find("G1"), rendered.find("G2"), rendered.find("G3")
    assert 0 <= pos1 < pos2 < pos3


# ---------- BudgetMeter ----------

def test_budget_meter_clips_at_100_percent() -> None:
    meter = BudgetMeter()
    # opus is over-budget by 50%; bar must still render fully filled (no overflow chars).
    state = LiveState(
        budget={
            "opus":   {"spent": 150.0, "ceiling": 100.0},
            "sonnet": {"spent":  10.0, "ceiling": 100.0},
            "haiku":  {"spent":   0.0, "ceiling": 100.0},
        }
    )
    rendered = meter.build_text(state).plain
    opus_bar = meter.bars["opus"]
    # all 20 cells filled, none empty
    assert opus_bar == "█" * 20
    assert "OVER" in rendered  # caller annotation for over-spend


def test_budget_meter_per_tier() -> None:
    meter = BudgetMeter()
    meter.build_text(LiveState())
    # one bar per Claude tier, in canonical order.
    assert list(meter.bars.keys()) == list(CLAUDE_TIERS)
    assert len(meter.bars) == 3


# ---------- App smoke ----------

@pytest.mark.asyncio
async def test_app_smoke() -> None:
    """Boot the full app under Textual's test pilot and assert all four widgets exist."""

    def fake_state() -> LiveState:
        return LiveState(
            events=[{"ts": "T", "kind": "ok"}],
            agents=[
                {"name": n, "fleet": f, "current_state": "idle", "last_action_ts": None}
                for f, names in AGENT_FLEETS.items()
                for n in names
            ],
            gates=[],
            budget={t: {"spent": 0.0, "ceiling": 100.0} for t in CLAUDE_TIERS},
        )

    app = AuroraStatusApp(state_loader=fake_state, refresh_interval=10.0)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Each widget type appears exactly once in the mounted tree.
        assert len(app.query(AgentGrid)) == 1
        assert len(app.query(GatesPane)) == 1
        assert len(app.query(EventTail)) == 1
        assert len(app.query(BudgetMeter)) == 1
