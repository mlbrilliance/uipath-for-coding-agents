"""T-G3d — Conductor functional contract test (meta fleet).

Asserts the four invariants the Conductor's prompt promises:

1. **Cross-fleet handoffs route through Conductor** — every adjacent pair
   of agents in a dispatch chain that crosses a fleet boundary must have
   ``conductor`` as one endpoint of the edge. (R.SW.02)
2. **HITL gate enforcement** — when a backlog candidate triggers a
   ``policy.yaml::gates`` entry, the plan must emit exactly one
   ``GateDecision`` with ``kind="hitl-required"``,
   ``concierge_dispatch=True``, ``next_state="awaiting-human"``. The gate
   name is read from the live ``policy.yaml`` so a policy edit cannot
   silently invalidate the test. (R.SW.05)
3. **Worktree allocation honours ``policy.yaml`` cap** — when the fleet
   already holds ``max_concurrent`` worktrees, the planner must not
   spawn additional worktrees; it must queue the deferred candidates.
   (R.SW.03 + governance discipline)
4. **Model-tier routing matches ``policy.yaml::routing.bindings``** —
   for every dispatch, the assigned model tier must equal the policy
   binding for that agent. The policy file is the only source of truth.
   (R.GOV)

The tests run **offline**: a deterministic ``ConductorPlanner`` shim
takes ``(backlog, fleet_state, policy)`` and returns a ``RoutingPlan``
the assertions inspect. No LLM calls, no network, no live UiPath.

Satisfies US-30.
"""
from __future__ import annotations

import json
import random
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.agents.contracts.conductor import (
    FLEET_OF,
    WORKTREE_AGENTS,
    Dispatch,
    GateDecision,
    RoutingPlan,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "policy.yaml"
FIXTURES = Path(__file__).parent / "fixtures" / "conductor"

DEFAULT_WORKTREE_CAP = 4


# --------------------------------------------------------------------------- #
# Deterministic planner shim — the system under test for this contract.
# --------------------------------------------------------------------------- #


class ConductorPlanner:
    """Deterministic stand-in for the Conductor's routing logic.

    The shim encodes only the four invariants the Conductor's prompt
    promises (cross-fleet mediation, gate enforcement, worktree cap,
    model-tier binding). It is *not* a faithful re-implementation of
    the runtime agent — it is the minimal piece of policy logic the
    contract test needs to assert against.
    """

    def __init__(self, policy: dict[str, Any]) -> None:
        self.policy = policy
        bindings = policy.get("routing", {}).get("bindings", {})
        if not isinstance(bindings, dict) or not bindings:
            raise ValueError("policy.yaml::routing.bindings is missing or empty")
        self.bindings: dict[str, str] = bindings
        self.gates: list[dict[str, Any]] = list(policy.get("gates") or [])
        pool = policy.get("worktree_pool") or {}
        self.worktree_cap: int = int(pool.get("max_concurrent", DEFAULT_WORKTREE_CAP))

    def plan(
        self, backlog: list[dict[str, Any]], fleet_state: dict[str, Any]
    ) -> RoutingPlan:
        random.seed(42)
        active_worktrees = sum(
            1
            for agent in fleet_state.get("agents", [])
            if agent.get("current_worktree")
        )
        capacity_remaining = max(0, self.worktree_cap - active_worktrees)

        dispatches: list[Dispatch] = []
        gate_decisions: list[GateDecision] = []
        spawned_worktrees: list[str] = []
        queued: list[str] = []
        chains: dict[str, list[str]] = {}

        for candidate in sorted(backlog, key=lambda c: c["id"]):
            chain = self._mediate_fleet_transitions(candidate["target_chain"])
            chains[candidate["id"]] = chain

            triggered = self._match_gate(candidate)
            if triggered is not None:
                gate_decisions.append(
                    GateDecision(
                        candidate_id=candidate["id"],
                        gate_name=triggered["name"],
                        kind="hitl-required",
                        concierge_dispatch=True,
                        next_state="awaiting-human",
                    )
                )
                continue

            worktree_path: str | None = None
            if candidate.get("requires_worktree", False):
                if capacity_remaining <= 0:
                    queued.append(candidate["id"])
                    continue
                worktree_path = f"${{AURORA_WORKTREE_DIR}}/{candidate['id']}/"
                spawned_worktrees.append(worktree_path)
                capacity_remaining -= 1

            for sequence, agent_name in enumerate(chain):
                dispatches.append(
                    Dispatch(
                        candidate_id=candidate["id"],
                        agent_name=agent_name,
                        fleet=FLEET_OF[agent_name],
                        model_tier=self.bindings[agent_name],
                        sequence=sequence,
                        worktree_path=(
                            worktree_path if agent_name in WORKTREE_AGENTS else None
                        ),
                    )
                )

        return RoutingPlan(
            dispatches=dispatches,
            gate_decisions=gate_decisions,
            spawned_worktrees=spawned_worktrees,
            queued=queued,
            dispatch_chain_by_candidate=chains,
        )

    @staticmethod
    def _mediate_fleet_transitions(target_chain: list[str]) -> list[str]:
        """Insert ``conductor`` between any two adjacent agents from different fleets.

        R.SW.02: cross-fleet handoffs go through Conductor. Single-fleet
        chains are returned unchanged.
        """
        if not target_chain:
            return []
        out = [target_chain[0]]
        for prev, curr in pairwise(target_chain):
            if FLEET_OF[prev] != FLEET_OF[curr] and "conductor" not in (prev, curr):
                out.append("conductor")
            out.append(curr)
        return out

    def _match_gate(self, candidate: dict[str, Any]) -> dict[str, Any] | None:
        gate_name = candidate.get("triggers_gate")
        if not gate_name:
            return None
        for gate in self.gates:
            if gate.get("name") == gate_name:
                return gate
        return None


# --------------------------------------------------------------------------- #
# Fixtures — read policy.yaml as ground truth, never mock it.
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def policy() -> dict[str, Any]:
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def planner(policy: dict[str, Any]) -> ConductorPlanner:
    return ConductorPlanner(policy)


@pytest.fixture(scope="module")
def synthetic_backlog() -> list[dict[str, Any]]:
    data = json.loads((FIXTURES / "synthetic_backlog.json").read_text(encoding="utf-8"))
    candidates = data["candidates"]
    assert len(candidates) >= 3, "synthetic_backlog.json must contain ≥3 candidates"
    fleets_seen = {FLEET_OF[a] for c in candidates for a in c["target_chain"]}
    assert len(fleets_seen) >= 2, "candidates must span more than one fleet"
    return candidates


@pytest.fixture(scope="module")
def idle_fleet_state() -> dict[str, Any]:
    return json.loads((FIXTURES / "fleet_state.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def over_capacity_state() -> dict[str, Any]:
    return json.loads((FIXTURES / "over_capacity_state.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def hitl_trigger_template() -> dict[str, Any]:
    return json.loads((FIXTURES / "hitl_gate_trigger.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Invariant 1 — cross-fleet handoffs route through Conductor (R.SW.02)
# --------------------------------------------------------------------------- #


def test_invariant_1_cross_fleet_routes_through_conductor(
    planner: ConductorPlanner,
    synthetic_backlog: list[dict[str, Any]],
    idle_fleet_state: dict[str, Any],
) -> None:
    plan = planner.plan(synthetic_backlog, idle_fleet_state)

    cross_fleet = next(
        (
            c
            for c in synthetic_backlog
            if len({FLEET_OF[a] for a in c["target_chain"]}) >= 2
        ),
        None,
    )
    assert cross_fleet is not None, (
        "synthetic_backlog must include at least one candidate whose "
        "target_chain crosses fleet boundaries (R.SW.02 has nothing to assert "
        "against otherwise)"
    )

    chain = plan.chain_for(cross_fleet["id"])
    assert chain, "cross-fleet candidate produced an empty dispatch chain"
    assert "conductor" in chain, (
        f"R.SW.02 violation: cross-fleet chain {chain} omits `conductor`. "
        f"Candidate={cross_fleet['id']!r}"
    )

    direct_cross_fleet_edges = [
        (prev, curr)
        for prev, curr in pairwise(chain)
        if FLEET_OF[prev] != FLEET_OF[curr] and "conductor" not in (prev, curr)
    ]
    assert not direct_cross_fleet_edges, (
        f"R.SW.02 violation: direct Discovery↔Build edges in chain {chain}: "
        f"{direct_cross_fleet_edges}"
    )

    fleets_in_chain = {FLEET_OF[a] for a in chain}
    assert {"discovery", "build"}.issubset(fleets_in_chain), (
        f"cross-fleet candidate {cross_fleet['id']!r} should span "
        f"discovery→build; chain fleets were {sorted(fleets_in_chain)}"
    )


# --------------------------------------------------------------------------- #
# Invariant 2 — HITL gate enforcement (R.SW.05)
# --------------------------------------------------------------------------- #


def test_invariant_2_hitl_gate_enforced_with_real_gate_name(
    planner: ConductorPlanner,
    policy: dict[str, Any],
    hitl_trigger_template: dict[str, Any],
    idle_fleet_state: dict[str, Any],
) -> None:
    real_gates = policy.get("gates") or []
    assert real_gates, "policy.yaml::gates is empty — invariant has nothing to bind to"
    real_gate_name = real_gates[0]["name"]

    candidate = dict(hitl_trigger_template["candidates"][0])
    candidate["triggers_gate"] = real_gate_name

    plan = planner.plan([candidate], idle_fleet_state)

    matching = [g for g in plan.gate_decisions if g.candidate_id == candidate["id"]]
    assert len(matching) == 1, (
        f"R.SW.05 violation: expected exactly one GateDecision for "
        f"{candidate['id']!r}; got {len(matching)} ({matching})"
    )

    decision = matching[0]
    assert decision.gate_name == real_gate_name, (
        f"GateDecision.gate_name {decision.gate_name!r} must equal the live "
        f"policy.yaml gate name {real_gate_name!r}"
    )
    assert decision.kind == "hitl-required"
    assert decision.concierge_dispatch is True
    assert decision.next_state == "awaiting-human"

    dispatched_for_candidate = [
        d for d in plan.dispatches if d.candidate_id == candidate["id"]
    ]
    assert dispatched_for_candidate == [], (
        "R.SW.05 absoluteness: when a gate fires, no specialist dispatches "
        f"may proceed for the candidate; got {dispatched_for_candidate}"
    )


def test_invariant_2_negative_path_no_decision_when_gate_absent(
    planner: ConductorPlanner,
    synthetic_backlog: list[dict[str, Any]],
    idle_fleet_state: dict[str, Any],
) -> None:
    """Error-path test (R.T.04): candidates without `triggers_gate` produce
    no GateDecision rows and *do* fan out into dispatches."""
    plan = planner.plan(synthetic_backlog, idle_fleet_state)

    no_gate_ids = {
        c["id"] for c in synthetic_backlog if not c.get("triggers_gate")
    }
    decisions_for_no_gate = [
        d for d in plan.gate_decisions if d.candidate_id in no_gate_ids
    ]
    assert decisions_for_no_gate == [], (
        f"R.SW.05 must not over-fire — got spurious decisions: "
        f"{decisions_for_no_gate}"
    )
    assert plan.dispatches, (
        "non-gated candidates must produce dispatches; got an empty plan"
    )


# --------------------------------------------------------------------------- #
# Invariant 3 — Worktree allocation honours policy.yaml cap (R.SW.03 + R.GOV)
# --------------------------------------------------------------------------- #


def test_invariant_3_over_capacity_defers_to_queue(
    planner: ConductorPlanner,
    policy: dict[str, Any],
    synthetic_backlog: list[dict[str, Any]],
    over_capacity_state: dict[str, Any],
) -> None:
    cap = (policy.get("worktree_pool") or {}).get(
        "max_concurrent", DEFAULT_WORKTREE_CAP
    )
    active = sum(
        1 for a in over_capacity_state["agents"] if a.get("current_worktree")
    )
    assert active >= cap, (
        f"over_capacity_state fixture broken: only {active} active worktrees "
        f"vs cap {cap}; the test cannot exercise the deferral path"
    )

    plan = planner.plan(synthetic_backlog, over_capacity_state)

    assert len(plan.spawned_worktrees) == 0, (
        f"R.SW.03 violation: planner spawned {plan.spawned_worktrees} "
        f"worktrees on top of {active} already-active ones (cap={cap})"
    )
    worktree_candidates = [
        c["id"] for c in synthetic_backlog if c.get("requires_worktree")
    ]
    assert worktree_candidates, (
        "synthetic_backlog must include ≥1 worktree-needing candidate so "
        "deferral is observable"
    )
    assert len(plan.queued) >= 1, (
        f"R.SW.03 violation: worktree-needing candidates {worktree_candidates} "
        f"should be queued, but plan.queued was {plan.queued}"
    )
    assert set(plan.queued).issubset(set(worktree_candidates)), (
        f"only worktree-needing candidates may queue; got {plan.queued} "
        f"vs eligible {worktree_candidates}"
    )


# --------------------------------------------------------------------------- #
# Invariant 4 — Model-tier routing matches policy.yaml::routing.bindings (R.GOV)
# --------------------------------------------------------------------------- #


def test_invariant_4_model_tier_matches_policy_bindings(
    planner: ConductorPlanner,
    policy: dict[str, Any],
    synthetic_backlog: list[dict[str, Any]],
    idle_fleet_state: dict[str, Any],
) -> None:
    bindings = policy["routing"]["bindings"]
    assert bindings, "policy.yaml::routing.bindings missing"

    plan = planner.plan(synthetic_backlog, idle_fleet_state)
    assert plan.dispatches, "no dispatches to assert routing against"

    mismatches: list[tuple[str, str, str]] = []
    for dispatch in plan.dispatches:
        expected = bindings.get(dispatch.agent_name)
        assert expected is not None, (
            f"agent {dispatch.agent_name!r} not bound in "
            f"policy.yaml::routing.bindings; the test cannot assert tier"
        )
        if dispatch.model_tier != expected:
            mismatches.append(
                (dispatch.agent_name, dispatch.model_tier, expected)
            )

    assert not mismatches, (
        "routing.bindings drift — (agent, planned_tier, policy_tier): "
        f"{mismatches}"
    )

    every_agent_in_chain = {
        agent
        for chain in plan.dispatch_chain_by_candidate.values()
        for agent in chain
    }
    assert every_agent_in_chain.issubset(bindings.keys()), (
        f"agents in dispatch chains have no binding in policy.yaml: "
        f"{sorted(every_agent_in_chain - bindings.keys())}"
    )


# --------------------------------------------------------------------------- #
# Determinism check — the shim must produce the same plan twice in a row
# (R.T.02 — testing the contract; same inputs → same outputs).
# --------------------------------------------------------------------------- #


def test_planner_is_deterministic(
    planner: ConductorPlanner,
    synthetic_backlog: list[dict[str, Any]],
    idle_fleet_state: dict[str, Any],
) -> None:
    first = planner.plan(synthetic_backlog, idle_fleet_state)
    second = planner.plan(synthetic_backlog, idle_fleet_state)
    assert first.model_dump() == second.model_dump(), (
        "ConductorPlanner is not deterministic; this breaks contract testing"
    )
