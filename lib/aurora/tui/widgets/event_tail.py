"""EventTail widget — tails the last N lines of events.jsonl with kind colouring."""
from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.widgets import Static

from aurora.tui.state import LiveState

_KIND_STYLES: dict[str, str] = {
    # green for nominal/positive events
    "ok": "green",
    "success": "green",
    "job_succeeded": "green",
    "deploy_succeeded": "green",
    # red for failures
    "failure": "red",
    "job_failed": "red",
    "maestro_instance_faulted": "red",
    "sentry_self_error": "red",
    "auth_failed": "red",
    # yellow for warnings
    "warning": "yellow",
    "drift_detected": "yellow",
}


def _style_for_kind(kind: str) -> str:
    if kind in _KIND_STYLES:
        return _KIND_STYLES[kind]
    if kind.endswith("_failed") or kind.endswith("_faulted") or kind.endswith("_error"):
        return "red"
    if kind.endswith("_succeeded") or kind.endswith("_ok"):
        return "green"
    return "default"


class EventTail(Static):
    """Tails ``events.jsonl`` and renders the last 50 lines coloured by ``kind``."""

    DEFAULT_CSS = """
    EventTail {
        height: 100%;
        border: solid $accent;
        padding: 0 1;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.border_title = "events"

    def build_text(self, state: LiveState) -> Text:
        text = Text()
        if not state.events:
            text.append("(no events)\n", style="dim")
        else:
            for evt in state.events:
                text.append(self._format_line(evt))
                text.append("\n")
        return text

    def update_state(self, state: LiveState) -> None:
        self._last_text: Text = self.build_text(state)
        if self.is_mounted:
            self.update(self._last_text)

    @property
    def last_text(self) -> Text:
        return getattr(self, "_last_text", Text())

    def _format_line(self, event: dict[str, Any]) -> Text:
        """Render a single event line as a rich ``Text`` styled by ``kind``.

        Exposed for unit tests — asserts can inspect the returned ``Text`` to
        verify per-kind colouring without spinning up a full Textual app.
        """
        kind = str(event.get("kind", ""))
        ts = str(event.get("ts", ""))
        scope = event.get("scope") or {}
        process = scope.get("process") or scope.get("instance_id") or ""
        msg = (event.get("details") or {}).get("message", "")
        style = _style_for_kind(kind)
        line = Text()
        line.append(f"{ts:<25} ", style="dim")
        line.append(f"{kind:<28}", style=style)
        if process:
            line.append(f" {process}", style="bold")
        if msg:
            line.append(f"  {msg[:80]}", style="dim")
        return line
