"""T-G3a — Analyst output contract tests.

Two recorded fixtures exercise the documented decision rules in
``agents/analyst.md``:

* ``clear_pdd.json``     — low ambiguity, score above threshold
                           → status ``ready-for-architect``,
                             ``ambiguity ∈ [0, 0.4)``
* ``ambiguous_pdd.json`` — high ambiguity, ``business_owner == 'unknown'``
                           → status ``needs-interviewer``,
                             ``ambiguity ∈ [0.4, 1.0]``

R.T.01: tests map to PDD acceptance criteria (ambiguity rubric, ROI score).
R.T.02: contract is asserted, not the code path.
R.T.04: ambiguous fixture is the mandatory error-path case.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from tests.agents.contracts.analyst import (
    AnalystArtefact,
    ProcessDefinition,
    RoiScore,
    parse_analyst_artefact,
)

FIXTURES = Path(__file__).parent / "fixtures" / "analyst"


def _load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_clear_pdd_validates_and_routes_to_architect() -> None:
    artefact = parse_analyst_artefact(_load("clear_pdd.json"))
    assert isinstance(artefact, AnalystArtefact)
    assert isinstance(artefact.pdd, ProcessDefinition)
    assert isinstance(artefact.roi, RoiScore)
    assert 0.0 <= artefact.pdd.ambiguity < 0.4, (
        f"clear PDD must have ambiguity < 0.4, got {artefact.pdd.ambiguity}"
    )
    assert artefact.pdd.business_owner != "unknown"
    assert isinstance(artefact.roi.score, int)
    assert artefact.roi.score >= 40, "score must clear default min_score_for_build"
    assert artefact.status == "ready-for-architect"


def test_ambiguous_pdd_routes_to_interviewer() -> None:
    artefact = parse_analyst_artefact(_load("ambiguous_pdd.json"))
    assert isinstance(artefact, AnalystArtefact)
    assert 0.4 <= artefact.pdd.ambiguity <= 1.0, (
        f"ambiguous PDD must have ambiguity ≥ 0.4, got {artefact.pdd.ambiguity}"
    )
    assert artefact.pdd.business_owner == "unknown" or artefact.pdd.ambiguity > 0.4
    assert artefact.status == "needs-interviewer"


@pytest.mark.parametrize(
    "fixture_name",
    ["clear_pdd.json", "ambiguous_pdd.json"],
    ids=["clear", "ambiguous"],
)
def test_pdd_has_three_or_more_acceptance_criteria(fixture_name: str) -> None:
    artefact = parse_analyst_artefact(_load(fixture_name))
    assert len(artefact.pdd.acceptance_criteria) >= 3, (
        "agents/analyst.md mandates ≥ 3 Given/When/Then criteria"
    )


def test_roi_weights_sum_to_one() -> None:
    artefact = parse_analyst_artefact(_load("clear_pdd.json"))
    total = sum(artefact.roi.weights.values())
    assert abs(total - 1.0) < 1e-6, f"weights must sum to 1.0, got {total}"
