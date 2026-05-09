"""AgentGrid widget — 19 cells, one per AURORA agent."""
from __future__ import annotations

from typing import Any

from rich.table import Table
from rich.text import Text
from textual.widgets import Static

from aurora.tui.state import AGENT_FLEETS, LiveState

# 19 agents = 5 discovery + 8 build + 5 operate + 1 meta.
_GRID_COLS = 4
_GRID_ROWS = 5  # 4 x 5 = 20, last cell left blank

_STATE_STYLE: dict[str, str] = {
    "idle": "dim",
    "busy": "yellow",
    "active": "green",
    "blocked": "red",
    "paused": "magenta",
}

_STATE_GLYPH: dict[str, str] = {
    "idle": "○",
    "busy": "◐",
    "active": "●",
    "blocked": "⚠",
    "paused": "⏸",
}


def _expected_agent_names() -> list[str]:
    out: list[str] = []
    for fleet in ("discovery", "build", "operate", "meta"):
        out.extend(AGENT_FLEETS[fleet])
    return out


class AgentGrid(Static):
    """Renders all 19 agents in a fixed 4x5 grid (the 20th cell is blank)."""

    DEFAULT_CSS = """
    AgentGrid {
        height: 100%;
        border: solid $accent;
        padding: 0 1;
    }
    """

    cols: int = _GRID_COLS
    rows: int = _GRID_ROWS

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.border_title = "agents (19)"
        self._cells: list[Text] = []

    @property
    def cells(self) -> list[Text]:
        """The list of currently-rendered cell contents (one per agent)."""
        return self._cells

    def build_table(self, state: LiveState) -> Table:
        """Build the grid table and refresh ``self.cells``. Pure — safe for tests."""
        by_name: dict[str, dict[str, Any]] = {a["name"]: a for a in state.agents}
        ordered = _expected_agent_names()
        cells: list[Text] = []
        for name in ordered:
            entry = by_name.get(name) or {"current_state": "idle", "last_action_ts": None}
            cells.append(self._format_cell(name, entry))
        self._cells = cells

        table = Table.grid(expand=True, padding=(0, 1))
        for _ in range(self.cols):
            table.add_column(ratio=1)
        for row_idx in range(self.rows):
            row = cells[row_idx * self.cols : (row_idx + 1) * self.cols]
            while len(row) < self.cols:
                row.append(Text(""))
            table.add_row(*row)
        return table

    def update_state(self, state: LiveState) -> None:
        table = self.build_table(state)
        if self.is_mounted:
            self.update(table)

    @staticmethod
    def _format_cell(name: str, entry: dict[str, Any]) -> Text:
        state = entry.get("current_state", "idle")
        ts = entry.get("last_action_ts") or "—"
        glyph = _STATE_GLYPH.get(state, "○")
        style = _STATE_STYLE.get(state, "dim")
        cell = Text()
        cell.append(f"{glyph} ", style=style)
        cell.append(f"{name}\n", style="bold")
        cell.append(f"  {state:<8} {ts}", style="dim")
        return cell
