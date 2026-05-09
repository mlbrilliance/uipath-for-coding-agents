"""AuroraStatusApp — Textual TUI shell for ``aurora status``.

A 2x2 grid:

    +------------------+--------------+
    |  AgentGrid       |  GatesPane   |
    +------------------+--------------+
    |  EventTail       |  BudgetMeter |
    +------------------+--------------+

The app refreshes every second from the live state collector. Refreshes are
synchronous and best-effort: if the underlying file disappears or is partial,
``load_state`` returns whatever it can and the widgets render empty placeholders.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from textual.app import App, ComposeResult
from textual.containers import Grid

from aurora.tui.state import LiveState, load_state
from aurora.tui.widgets.agent_grid import AgentGrid
from aurora.tui.widgets.budget_meter import BudgetMeter
from aurora.tui.widgets.event_tail import EventTail
from aurora.tui.widgets.gates_pane import GatesPane


class AuroraStatusApp(App[None]):
    """Four-pane TUI for the swarm. Read-only; ``q`` quits."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 2 2;
        grid-gutter: 1;
        padding: 1;
    }
    AgentGrid, GatesPane, EventTail, BudgetMeter {
        height: 100%;
    }
    """

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("q", "quit", "quit"),
        ("r", "refresh_now", "refresh"),
    ]

    def __init__(
        self,
        *args: Any,
        aurora_home: Path | None = None,
        state_loader: Any = None,
        refresh_interval: float = 1.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._aurora_home = aurora_home
        self._state_loader = state_loader or (lambda: load_state(self._aurora_home))
        self._refresh_interval = refresh_interval
        self._agent_grid = AgentGrid()
        self._gates_pane = GatesPane()
        self._event_tail = EventTail()
        self._budget_meter = BudgetMeter()

    def compose(self) -> ComposeResult:
        with Grid():
            yield self._agent_grid
            yield self._gates_pane
            yield self._event_tail
            yield self._budget_meter

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(self._refresh_interval, self._refresh)

    def action_refresh_now(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        try:
            state: LiveState = self._state_loader()
        except Exception:
            # TUI must not die on a transient read error; render a blank slate.
            state = LiveState()
        self._agent_grid.update_state(state)
        self._gates_pane.update_state(state)
        self._event_tail.update_state(state)
        self._budget_meter.update_state(state)
