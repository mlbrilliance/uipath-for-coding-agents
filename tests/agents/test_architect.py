"""T-G3b — Architect contract test.

Loads a recorded PDD fixture, runs an offline shim that replays the
Architect's `agents/architect.md` decision rubric, and asserts the
emitted ADR validates against `tests/agents/contracts/architect.ADR`.

Discipline cited:
    R.T.02   — assert the contract, not the code path.
    R.SW.06.1 — `skill_picks` must come from the official UiPath catalogue.

Satisfies US-8, US-9, US-31.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.agents.contracts.architect import ADR, Pattern

FIXTURES = Path(__file__).parent / "fixtures" / "architect"


def _decide(pdd: dict) -> dict:
    """Tiny offline shim mirroring `agents/architect.md` decision rubric.

    Maestro when ≥ 2 actor types collaborate; otherwise pick the agent
    framework hint from the PDD.
    """
    actor_types = set(pdd.get("actor_types", []))
    if len(actor_types) >= 2:
        return {
            "pattern": Pattern.MAESTRO.value,
            "forgers": ["forger-maestro", "forger-rpa", "forger-coded", "forger-agent"],
            "rationale": (
                "Multiple actor types (agent + RPA + human) collaborate; "
                "Maestro is the orchestrator that fits."
            ),
            "skill_picks": [
                "uipath-platform",
                "uipath-rpa-workflows",
                "uipath-coded-workflows",
                "uipath-coded-agents",
            ],
        }
    return {
        "pattern": Pattern.CODED_AGENT_LANGGRAPH.value,
        "forgers": ["forger-agent"],
        "rationale": "Single-agent reasoning loop over unstructured input; LangGraph fits.",
        "skill_picks": ["uipath-coded-agents", "uipath-platform"],
    }


@pytest.mark.parametrize(
    ("fixture_name", "expected_pattern"),
    [
        ("maestro_pdd.json", Pattern.MAESTRO),
        ("coded_agent_pdd.json", Pattern.CODED_AGENT_LANGGRAPH),
    ],
)
def test_architect_emits_valid_adr(fixture_name: str, expected_pattern: Pattern) -> None:
    pdd = json.loads((FIXTURES / fixture_name).read_text())
    adr = ADR.model_validate(_decide(pdd))
    assert adr.pattern is expected_pattern
    assert adr.forgers, "ADR must list at least one forger"
    assert adr.skill_picks, "ADR must list at least one skill"


def test_architect_skill_picks_must_be_official() -> None:
    """R.SW.06.1: invented skill names are an instant contract failure."""
    bad = {
        "pattern": Pattern.MAESTRO.value,
        "forgers": ["forger-maestro"],
        "rationale": "valid rationale text",
        "skill_picks": ["uipath-platform", "made-up-skill"],
    }
    with pytest.raises(ValueError, match=r"R\.SW\.06\.1"):
        ADR.model_validate(bad)


def test_architect_rejects_unknown_forger() -> None:
    bad = {
        "pattern": Pattern.MAESTRO.value,
        "forgers": ["forger-maestro", "forger-imaginary"],
        "rationale": "valid rationale text",
        "skill_picks": ["uipath-platform"],
    }
    with pytest.raises(ValueError, match="unknown forger"):
        ADR.model_validate(bad)
