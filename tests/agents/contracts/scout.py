"""Scout contract — FrictionSignal.

Mirrors the JSON object Scout emits to `curator` on stdout, as documented
in `agents/scout.md`. The raw Scout payload uses nested `signal.*` fields;
the parser shim flattens those into a normalised FrictionSignal that
downstream Discovery agents can rely on.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FrequencyHint = Literal[
    "daily", "weekly", "monthly", "quarterly", "ad-hoc", "unknown"
]

SOURCE_PREFIXES: tuple[str, ...] = ("slack:", "jira:", "imap:", "calendar:", "transcript:")


class FrictionSignal(BaseModel):
    """A single friction signal surfaced by Scout.

    Field semantics:
        source: provenance prefix + locator, e.g. ``slack:#rpa-asks``.
        text: the raw human-authored sentence(s) the signal was extracted from.
        frequency_hint: cadence keyword (see ``FrequencyHint``).
        pain_hint: short verb-phrase summarising the pain ("manual copy-paste").
        actor: who experiences the friction (user id, email, or human-readable).
        timestamp: ISO-8601 UTC instant the source line was authored.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: str = Field(min_length=3)
    text: str = Field(min_length=1)
    frequency_hint: FrequencyHint
    pain_hint: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    timestamp: datetime

    @field_validator("source")
    @classmethod
    def _source_has_known_prefix(cls, value: str) -> str:
        if not any(value.startswith(prefix) for prefix in SOURCE_PREFIXES):
            raise ValueError(
                f"source {value!r} must start with one of {SOURCE_PREFIXES}"
            )
        return value


def parse_friction_signal(payload: dict[str, Any]) -> FrictionSignal:
    """Deterministic shim that mirrors Scout's documented output contract.

    Accepts both the nested raw shape (``{raw, signal: {...}}``) and the
    already-flattened shape — Scout's prose contract only fixes the
    semantic fields, not their physical nesting.
    """
    if "signal" in payload and isinstance(payload["signal"], dict):
        nested = payload["signal"]
        flat: dict[str, Any] = {
            "source": payload.get("source"),
            "text": payload.get("raw") or payload.get("text"),
            "frequency_hint": nested.get("frequency_hint"),
            "pain_hint": nested.get("pain_hint")
            or (", ".join(nested["pain_indicators"]) if nested.get("pain_indicators") else None),
            "actor": nested.get("actor"),
            "timestamp": payload.get("ts") or payload.get("timestamp"),
        }
        return FrictionSignal.model_validate(flat)
    return FrictionSignal.model_validate(payload)
