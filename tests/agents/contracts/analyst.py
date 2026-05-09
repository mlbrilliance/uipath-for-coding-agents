"""Analyst contract — PDD shape + ROI score.

Mirrors the two artefacts Analyst writes per ``agents/analyst.md``:

* a ``ProcessDefinition`` — PDD essentials (process name, owner, trigger,
  inputs/outputs, actors, acceptance criteria, ambiguity score)
* a ``RoiScore`` — frequency * pain * feasibility weighted score

The combined ``AnalystArtefact`` resolves the candidate's next status:
``needs-interviewer``, ``ready-for-architect`` or ``rejected``.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AmbiguityFloat = float

AnalystStatus = Literal["needs-interviewer", "ready-for-architect", "rejected"]
TriggerKind = Literal["event", "schedule", "on-demand"]
ActorKind = Literal["user", "rpa-bot", "ai-agent", "external-system"]
AMBIGUITY_INTERVIEWER_THRESHOLD = 0.4


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    given: str = Field(min_length=1)
    when: str = Field(min_length=1)
    then: str = Field(min_length=1)


class ProcessDefinition(BaseModel):
    """The structured PDD shape Analyst writes to ``pdd.md``."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    process_name: str = Field(pattern=r"^[A-Z][A-Za-z0-9]+$")
    business_owner: str = Field(min_length=1)
    trigger: TriggerKind
    inputs: list[str] = Field(min_length=1)
    outputs: list[str] = Field(min_length=1)
    actors: list[ActorKind] = Field(min_length=1)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=3)
    out_of_scope: list[str]
    ambiguity: AmbiguityFloat = Field(ge=0.0, le=1.0)


class RoiScore(BaseModel):
    """The ``roi.json`` companion artefact."""

    model_config = ConfigDict(extra="forbid")

    frequency: float = Field(ge=0.0, le=1.0)
    pain: float = Field(ge=0.0, le=1.0)
    feasibility: float = Field(ge=0.0, le=1.0)
    weights: dict[str, float]
    score: int = Field(ge=0, le=100)
    rationale: str = Field(min_length=1)

    @field_validator("weights")
    @classmethod
    def _weights_sum_to_one(cls, value: dict[str, float]) -> dict[str, float]:
        required = {"frequency", "pain", "feasibility"}
        if set(value) != required:
            raise ValueError(f"weights keys must be exactly {sorted(required)}")
        if abs(sum(value.values()) - 1.0) > 1e-6:
            raise ValueError("weights must sum to 1.0")
        return value


class AnalystArtefact(BaseModel):
    """Combined PDD + ROI artefact, with the next-state status."""

    model_config = ConfigDict(extra="forbid")

    pdd: ProcessDefinition
    roi: RoiScore
    status: AnalystStatus


def parse_analyst_artefact(payload: dict[str, Any]) -> AnalystArtefact:
    """Deterministic shim that mirrors Analyst's documented decision rules.

    Status derivation per ``agents/analyst.md``:

    * ``ambiguity > 0.4`` OR ``business_owner == 'unknown'`` → needs-interviewer
    * else if ``score >= min_score_for_build`` (40 by default)  → ready-for-architect
    * else                                                       → rejected
    """
    pdd = ProcessDefinition.model_validate(payload["pdd"])
    roi = RoiScore.model_validate(payload["roi"])
    min_score: int = int(payload.get("min_score_for_build", 40))
    if pdd.ambiguity > AMBIGUITY_INTERVIEWER_THRESHOLD or pdd.business_owner == "unknown":
        status: AnalystStatus = "needs-interviewer"
    elif roi.score >= min_score:
        status = "ready-for-architect"
    else:
        status = "rejected"
    return AnalystArtefact(pdd=pdd, roi=roi, status=status)
