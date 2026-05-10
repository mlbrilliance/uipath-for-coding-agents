"""Architect ADR contract.

Encodes the Architecture Decision Record shape promised by
`agents/architect.md`. The Architect is the swarm's only pattern picker;
its output gates the entire Build fleet, so we lock the shape down in
pydantic v2 and parametrise the tests against PDD fixtures.

Discipline cited:
    R.SW.06.1 — `skill_picks` must reference the canonical UiPath skill
                catalogue (or AURORA's local extensions). Anything else
                is a contract violation.
    R.T.02   — tests assert the contract, not the code path.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Pattern(str, Enum):
    """Pattern names the Architect is allowed to pick.

    Mirrors the rubric in `agents/architect.md` — adding a new pattern
    here is a deliberate contract change, not an Architect decision.
    """

    SEQUENCE = "Sequence"
    REFRAMEWORK_PERFORMER = "REFramework-Performer"
    REFRAMEWORK_DISPATCHER = "REFramework-Dispatcher"
    CODED_WORKFLOW = "Coded-Workflow"
    CODED_AGENT_LANGGRAPH = "Coded-Agent-LangGraph"
    CODED_AGENT_OPENAI_AGENTS = "Coded-Agent-OpenAIAgents"
    CODED_AGENT_LLAMAINDEX = "Coded-Agent-LlamaIndex"
    MAESTRO = "Maestro"
    ACTION_CENTER = "Action-Center"


VALID_FORGERS: frozenset[str] = frozenset(
    {"forger-rpa", "forger-coded", "forger-agent", "forger-maestro"}
)

OFFICIAL_UIPATH_SKILLS: frozenset[str] = frozenset(
    {
        "uipath-rpa-workflows",
        "uipath-coded-workflows",
        "uipath-coded-agents",
        "uipath-flow",
        "uipath-platform",
        "uipath-coded-apps",
        "uipath-servo",
    }
)


class ADR(BaseModel):
    """Architecture Decision Record — the only thing the Architect emits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    pattern: Pattern
    forgers: Annotated[list[str], Field(min_length=1)]
    rationale: Annotated[str, Field(min_length=10)]
    skill_picks: Annotated[list[str], Field(min_length=1)]

    @field_validator("forgers")
    @classmethod
    def _forgers_must_be_known(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - VALID_FORGERS)
        if unknown:
            raise ValueError(f"unknown forger(s): {unknown}; allowed: {sorted(VALID_FORGERS)}")
        return value

    @field_validator("skill_picks")
    @classmethod
    def _skills_must_exist(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - OFFICIAL_UIPATH_SKILLS)
        if unknown:
            raise ValueError(
                f"R.SW.06.1: skill_picks must come from the official UiPath catalogue; "
                f"unknown: {unknown}"
            )
        return value
