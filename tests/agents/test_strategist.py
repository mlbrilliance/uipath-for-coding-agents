"""T-G3a — Strategist output contract tests.

The quarterly fixture covers all four documented recommendation kinds
from ``agents/strategist.md``: ``consolidate``, ``deprecate``,
``prioritise``, ``invest``. Asserts the report carries ≥ 1
recommendation, that each one matches the closed ``kind`` set, and that
it carries a non-empty ``target_id`` and ``rationale``.

R.T.01: tests map to strategist's decision rubric.
R.T.04: an off-rubric ``kind`` is exercised via in-test mutation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from tests.agents.contracts.strategist import (
    Recommendation,
    RecommendationKind,
    StrategyReport,
    parse_strategy_report,
)

FIXTURES = Path(__file__).parent / "fixtures" / "strategist"

ALLOWED_KINDS: set[RecommendationKind] = {
    "consolidate", "deprecate", "prioritise", "invest"
}


def _load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_strategy_report_validates() -> None:
    report = parse_strategy_report(_load("quarterly.json"))
    assert isinstance(report, StrategyReport)
    assert report.period
    assert len(report.recommendations) >= 1, (
        "agents/strategist.md mandates ≥ 1 recommendation per run"
    )


def test_every_recommendation_has_required_shape() -> None:
    report = parse_strategy_report(_load("quarterly.json"))
    for rec in report.recommendations:
        assert isinstance(rec, Recommendation)
        assert rec.kind in ALLOWED_KINDS
        assert rec.target_id, "target_id must be non-empty"
        assert rec.rationale, "rationale must be non-empty"


def test_all_four_recommendation_kinds_are_supported() -> None:
    report = parse_strategy_report(_load("quarterly.json"))
    seen = {rec.kind for rec in report.recommendations}
    assert seen == ALLOWED_KINDS, (
        f"fixture should exercise all four documented kinds; saw {sorted(seen)}"
    )


def test_off_rubric_kind_is_rejected() -> None:
    payload = _load("quarterly.json")
    payload["recommendations"][0]["kind"] = "expand"
    with pytest.raises(ValidationError) as exc:
        parse_strategy_report(payload)
    assert any(
        "kind" in ".".join(str(p) for p in err["loc"]) for err in exc.value.errors()
    ), f"expected violation on `kind` field; got {exc.value.errors()}"


@pytest.mark.parametrize("kind", sorted(ALLOWED_KINDS))
def test_each_documented_kind_can_round_trip(kind: RecommendationKind) -> None:
    rec = Recommendation(kind=kind, target_id=f"T-{kind}", rationale=f"reason for {kind}")
    assert rec.kind == kind
