"""Pydantic v2 contracts for the Conductor functional test (T-G3d).

The four shapes here are what ``ConductorPlanner.plan`` returns and what the
four invariant assertions in ``tests/agents/test_conductor.py`` consume.

The contracts deliberately model the **observable** outputs of the
Conductor's responsibilities (cross-fleet routing, gate enforcement,
worktree allocation, model-tier assignment); they don't try to model the
agent's prompt-side reasoning.

Per CLAUDE.md the closed agent set is 19. ``FLEET_OF`` mirrors the
``fleet:`` frontmatter field across ``agents/*.md`` and is the planner's
ground truth for "what fleet does agent X belong to" without re-parsing
markdown for every dispatch.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Fleet = Literal["discovery", "build", "operate", "meta"]
ModelTier = Literal["high_stakes", "mid_stakes", "continuous"]
GateKind = Literal["hitl-required", "auto-approved", "skipped"]
NextState = Literal["awaiting-human", "proceed", "blocked"]


FLEET_OF: dict[str, Fleet] = {
    "scout": "discovery",
    "curator": "discovery",
    "analyst": "discovery",
    "interviewer": "discovery",
    "strategist": "discovery",
    "architect": "build",
    "cartographer": "build",
    "forger-rpa": "build",
    "forger-coded": "build",
    "forger-agent": "build",
    "forger-maestro": "build",
    "reviewer": "build",
    "tester": "build",
    "sentry": "operate",
    "diagnostician": "operate",
    "surgeon": "operate",
    "auditor": "operate",
    "concierge": "operate",
    "conductor": "meta",
}


WORKTREE_AGENTS: frozenset[str] = frozenset(
    {
        "forger-rpa",
        "forger-coded",
        "forger-agent",
        "forger-maestro",
        "surgeon",
    }
)


class Dispatch(BaseModel):
    """One Conductor → specialist agent invocation in the plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    fleet: Fleet
    model_tier: ModelTier
    sequence: int = Field(ge=0)
    worktree_path: str | None = None


class GateDecision(BaseModel):
    """A HITL gate evaluation outcome for a single backlog candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    gate_name: str = Field(min_length=1)
    kind: GateKind
    concierge_dispatch: bool
    next_state: NextState


class RoutingPlan(BaseModel):
    """The deterministic Conductor plan — every assertion in the test reads from here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dispatches: list[Dispatch]
    gate_decisions: list[GateDecision]
    spawned_worktrees: list[str]
    queued: list[str]
    dispatch_chain_by_candidate: dict[str, list[str]]

    def chain_for(self, candidate_id: str) -> list[str]:
        return self.dispatch_chain_by_candidate[candidate_id]
