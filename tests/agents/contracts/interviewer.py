"""Interviewer contract — bounded QuestionSet.

Mirrors the at-most-five questions Interviewer routes via Concierge per
``agents/interviewer.md``. The contract enforces the documented upper
bound (≤ 5) and the per-question shape (`text`, `asked_to`, `blocking`).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

INTERVIEWER_MAX_QUESTIONS = 5


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1)
    asked_to: str = Field(min_length=1)
    blocking: bool


class QuestionSet(BaseModel):
    """At-most-five Socratic questions for a single interview round."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(min_length=3)
    questions: list[Question] = Field(
        min_length=1, max_length=INTERVIEWER_MAX_QUESTIONS
    )


def parse_question_set(payload: dict[str, Any]) -> QuestionSet:
    """Deterministic shim — pure schema validation, no LLM calls."""
    return QuestionSet.model_validate(payload)
