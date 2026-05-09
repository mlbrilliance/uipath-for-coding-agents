"""GatesPane widget — pending HITL Action Center gates with deadline countdowns."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from rich.text import Text
from textual.widgets import Static

from aurora.tui.state import LiveState

EMPTY_MESSAGE = "No HITL gates pending."


def _parse_deadline(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        # Tolerate trailing 'Z'
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _format_remaining(deadline: datetime | None, now: datetime) -> str:
    if deadline is None:
        return "—"
    delta = deadline - now
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return "expired"
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours:
        return f"in {hours}h {minutes:02d}m"
    return f"in {minutes}m"


def _sort_key(gate: dict[str, Any]) -> tuple[int, datetime]:
    dl = _parse_deadline(gate.get("deadline"))
    if dl is None:
        # Gates without a deadline sort last but stay stable.
        return (1, datetime.max.replace(tzinfo=UTC))
    return (0, dl)


class GatesPane(Static):
    """Lists pending HITL gates sorted by deadline ascending."""

    DEFAULT_CSS = """
    GatesPane {
        height: 100%;
        border: solid $warning;
        padding: 0 1;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.border_title = "gates"

    def build_text(self, state: LiveState, now: datetime | None = None) -> Text:
        """Build the rich ``Text`` for this state without touching widget state.

        Exposed for unit tests that don't want to mount a Textual app.
        """
        now = now or datetime.now(UTC)
        gates = sorted(state.gates, key=_sort_key)
        text = Text()
        if not gates:
            text.append(EMPTY_MESSAGE, style="dim")
            return text
        for gate in gates:
            kind = gate.get("kind", "gate")
            cand = gate.get("candidate") or gate.get("id") or ""
            approver = gate.get("approver", "")
            deadline = _parse_deadline(gate.get("deadline"))
            remaining = _format_remaining(deadline, now)
            text.append(f"{kind}", style="bold yellow")
            if cand:
                text.append(f"  {cand}\n", style="default")
            else:
                text.append("\n", style="default")
            if approver:
                text.append(f"  approver {approver}\n", style="dim")
            text.append(f"  timeout  {remaining}\n", style="dim")
        return text

    def update_state(self, state: LiveState, now: datetime | None = None) -> None:
        self._last_text: Text = self.build_text(state, now=now)
        if self.is_mounted:
            self.update(self._last_text)

    @property
    def last_text(self) -> Text:
        """The most recently built renderable. Empty Text before first update."""
        return getattr(self, "_last_text", Text())
