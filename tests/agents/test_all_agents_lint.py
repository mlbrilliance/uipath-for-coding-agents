"""T-G4 — Reviewer-driven heuristic lint over every ``agents/<name>.md``.

Codifies the senior-RPA-developer review heuristics (rules R.G4.01-R.G4.10)
that the Reviewer agent would otherwise apply at runtime. Runs offline,
deterministic, no LLM calls — same pattern as T-G1/T-G2/T-G3.

Two parametrised test families:

* :func:`test_agent_passes_reviewer_lint` — runs every rule against every
  agent file and surfaces ``severity == "error"`` violations.
* :func:`test_rule_catches_synthetic_offender` — proves each rule is real
  by feeding it its own synthetic offender (R.T.04 mandates error-path
  tests for every rule).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.agents.reviewer_rules import REVIEWER_RULES, ReviewerRule, lint_agent_file

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_FILES = sorted((REPO_ROOT / "agents").glob("*.md"))


@pytest.mark.parametrize("agent_path", AGENT_FILES, ids=lambda p: p.stem)
def test_agent_passes_reviewer_lint(agent_path: Path) -> None:
    """Every agent must clear all error-severity rules R.G4.01-R.G4.10."""
    violations = lint_agent_file(agent_path)
    error_violations = [v for v in violations if v.severity == "error"]
    assert not error_violations, "\n".join(str(v) for v in error_violations)


@pytest.mark.parametrize("rule", REVIEWER_RULES, ids=lambda r: r.id)
def test_rule_catches_synthetic_offender(rule: ReviewerRule) -> None:
    """Each rule must reject its own synthetic offender to prove the
    enforcement is real (R.T.04 — error-path tests are mandatory)."""
    assert rule.synthetic_offender_caught(), (
        f"rule {rule.id} would not catch its own synthetic offender"
    )
