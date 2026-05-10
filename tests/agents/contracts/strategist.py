"""Strategist contract — Recommendation set.

Mirrors the quarterly portfolio recommendations Strategist writes to
``.aurora/strategy/<date>.md`` per ``agents/strategist.md``. Each entry
has a closed ``kind`` from {consolidate, deprecate, prioritise, invest},
a target identifier, and a free-text rationale.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RecommendationKind = Literal["consolidate", "deprecate", "prioritise", "invest"]


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: RecommendationKind
    target_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)


class StrategyReport(BaseModel):
    """A full quarterly (or nightly) Strategist report."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    period: str = Field(min_length=4)
    recommendations: list[Recommendation] = Field(min_length=1)


def parse_strategy_report(payload: dict[str, Any]) -> StrategyReport:
    """Deterministic shim — schema validation only.

    Strategist's prose contract guarantees ≥ 1 recommendation per run; the
    pydantic ``min_length=1`` enforces that at validation time.
    """
    return StrategyReport.model_validate(payload)
