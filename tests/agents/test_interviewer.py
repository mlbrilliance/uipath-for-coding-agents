"""T-G3a — Interviewer output contract tests.

The fixture is an analyst-flagged candidate with a 4-question round.
Asserts the contract from ``agents/interviewer.md``:

* ``≤ 5`` questions per round
* each question: ``{text, asked_to: str, blocking: bool}``
* no LLM call — the parser is pure schema validation

R.T.02: contract-only; we don't exercise the routing-via-Concierge path.
R.T.04: a sixth-question fixture would exceed the cap → exercised via the
        in-test mutation below.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from tests.agents.contracts.interviewer import (
    INTERVIEWER_MAX_QUESTIONS,
    Question,
    QuestionSet,
    parse_question_set,
)

FIXTURES = Path(__file__).parent / "fixtures" / "interviewer"


def _load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_interviewer_question_set_validates() -> None:
    payload = _load("needs_info.json")
    qset = parse_question_set(payload)
    assert isinstance(qset, QuestionSet)
    assert qset.candidate_id.startswith("C")
    assert 1 <= len(qset.questions) <= INTERVIEWER_MAX_QUESTIONS


def test_each_question_has_required_fields() -> None:
    qset = parse_question_set(_load("needs_info.json"))
    for q in qset.questions:
        assert isinstance(q, Question)
        assert q.text and isinstance(q.text, str)
        assert q.asked_to and isinstance(q.asked_to, str)
        assert isinstance(q.blocking, bool)


def test_six_questions_violate_the_max_five_cap() -> None:
    payload = _load("needs_info.json")
    payload["questions"] = (payload["questions"] + payload["questions"])[:6]
    with pytest.raises(ValidationError) as exc:
        parse_question_set(payload)
    assert any("at most 5" in err["msg"].lower() or "max_length" in err["type"]
               for err in exc.value.errors()), (
        f"expected a max-length violation; got {exc.value.errors()}"
    )
