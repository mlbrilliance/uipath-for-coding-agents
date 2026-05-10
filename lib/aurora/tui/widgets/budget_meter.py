"""BudgetMeter widget — daily token spend per Claude tier vs policy ceilings."""
from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.widgets import Static

from aurora.tui.state import CLAUDE_TIERS, LiveState

_BAR_WIDTH = 20


def _bar(fraction: float, width: int = _BAR_WIDTH) -> tuple[str, str]:
    """Return (bar_text, style) for a fraction in [0, ∞).

    Clips at 100%: even an over-spend renders a fully-filled bar (and is
    annotated by the caller as ``OVER``).
    """
    clipped = max(0.0, min(1.0, fraction))
    filled = round(clipped * width)
    bar = "█" * filled + "·" * (width - filled)
    if fraction >= 1.0:
        style = "bold red"
    elif fraction >= 0.8:
        style = "yellow"
    else:
        style = "green"
    return bar, style


class BudgetMeter(Static):
    """Renders one ASCII progress bar per Claude tier (Opus / Sonnet / Haiku)."""

    DEFAULT_CSS = """
    BudgetMeter {
        height: 100%;
        border: solid $secondary;
        padding: 0 1;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.border_title = "budget today"
        self._bars: dict[str, str] = {}

    @property
    def bars(self) -> dict[str, str]:
        """Last-rendered bar string per tier — exposed for tests."""
        return self._bars

    def build_text(self, state: LiveState) -> Text:
        """Build the rich ``Text`` and refresh ``self.bars``. Pure — safe for tests."""
        text = Text()
        self._bars = {}
        for tier in CLAUDE_TIERS:
            entry: dict[str, Any] = state.budget.get(tier) or {}
            spent = float(entry.get("spent", 0.0))
            ceiling = float(entry.get("ceiling", 0.0))
            fraction = (spent / ceiling) if ceiling > 0 else 0.0
            bar, style = _bar(fraction)
            self._bars[tier] = bar
            label = tier.capitalize()
            text.append(f"{label:<7}", style="bold")
            text.append(f" {bar} ", style=style)
            if ceiling > 0:
                text.append(
                    f"{spent:>6.2f} / {ceiling:>6.2f}",
                    style="dim",
                )
            else:
                text.append(f"{spent:>6.2f}", style="dim")
            if fraction > 1.0:
                text.append("  OVER", style="bold red")
            text.append("\n")
        return text

    def update_state(self, state: LiveState) -> None:
        self._last_text: Text = self.build_text(state)
        if self.is_mounted:
            self.update(self._last_text)

    @property
    def last_text(self) -> Text:
        return getattr(self, "_last_text", Text())
