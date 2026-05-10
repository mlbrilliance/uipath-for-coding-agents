"""T-G4 — per-rule unit tests for the Reviewer-style heuristic lint.

Each ``rule_g4_*`` function in :mod:`tests.agents.reviewer_rules` is
covered here in isolation against:

* a hand-crafted **offender fixture** that must surface exactly one
  violation at the rule's declared severity (R.T.04 — error-path tests
  are mandatory);
* a hand-crafted **clean fixture** that must surface zero violations
  for the same rule (sanity check that the rule doesn't false-positive
  on benign prompts).

This file is the refactor-step companion to
``test_all_agents_lint.py``: the parametrised test there proves every
agent passes the suite end-to-end, while these unit tests pin down
each rule's intent so future contributors can extend the rule set
without regressing the others.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.agents import reviewer_rules as rr
from tests.agents.contracts.violation import Violation

# A bare-minimum agent file that satisfies every rule. Individual unit
# tests mutate this skeleton to inject a single targeted offender.
_CLEAN_FRONTMATTER = (
    "---\n"
    "name: scout\n"
    "description: stub\n"
    "tools: Read, Bash, Glob, Grep\n"
    "model: haiku\n"
    "fleet: discovery\n"
    "model_tier: continuous\n"
    "---\n"
)
_CLEAN_BODY = (
    "## Inputs\n\nbacklog seed.\n\n"
    "## What you do\n\nObserve. Hand off to curator.\n\n"
    "## Output\n\nDone when emitted.\n"
)
_CLEAN_AGENT = _CLEAN_FRONTMATTER + _CLEAN_BODY


SCOUT_PATH = rr.AGENTS_DIR / "scout.md"
ARCHITECT_PATH = rr.AGENTS_DIR / "architect.md"
SURGEON_PATH = rr.AGENTS_DIR / "surgeon.md"


def _violations_for(rule: rr.ReviewerRule, text: str, path: Path = SCOUT_PATH) -> list[Violation]:
    return [v for v in rule.check(path, text) if v.rule_id == rule.id]


def _rule(rule_id: str) -> rr.ReviewerRule:
    for r in rr.REVIEWER_RULES:
        if r.id == rule_id:
            return r
    raise KeyError(rule_id)


# --------------------------------------------------------------------------- #
# R.G4.01 — frontmatter present
# --------------------------------------------------------------------------- #


def test_g4_01_clean_passes() -> None:
    rule = _rule("R.G4.01")
    assert _violations_for(rule, _CLEAN_AGENT) == []


def test_g4_01_offender_caught() -> None:
    rule = _rule("R.G4.01")
    bad = "no fence here\n\n## Inputs\n\nstub\n"
    found = _violations_for(rule, bad)
    assert len(found) == 1 and found[0].severity == "error"


# --------------------------------------------------------------------------- #
# R.G4.02 — body has >= 3 ## sections
# --------------------------------------------------------------------------- #


def test_g4_02_clean_passes() -> None:
    rule = _rule("R.G4.02")
    assert _violations_for(rule, _CLEAN_AGENT) == []


def test_g4_02_offender_caught() -> None:
    rule = _rule("R.G4.02")
    bad = _CLEAN_FRONTMATTER + "Single paragraph, no sections at all. Hand off to curator. backlog.\n"
    found = _violations_for(rule, bad)
    assert len(found) == 1 and found[0].severity == "error"


def test_g4_02_ignores_third_level_headers() -> None:
    """Only ``## `` counts; ``### `` does not satisfy the floor."""
    rule = _rule("R.G4.02")
    bad = (
        _CLEAN_FRONTMATTER
        + "## Only one\n\n### sub\n\n### sub\n\n### sub\n\nbacklog. Hand off to curator.\n"
    )
    found = _violations_for(rule, bad)
    assert len(found) == 1


# --------------------------------------------------------------------------- #
# R.G4.03 — no first-person plural pronouns
# --------------------------------------------------------------------------- #


def test_g4_03_clean_passes() -> None:
    rule = _rule("R.G4.03")
    assert _violations_for(rule, _CLEAN_AGENT) == []


def test_g4_03_catches_we() -> None:
    rule = _rule("R.G4.03")
    bad = _CLEAN_FRONTMATTER + (
        "## A\n\nWe should run this. backlog. Hand off to curator.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    found = _violations_for(rule, bad)
    assert len(found) == 1 and found[0].severity == "error"
    assert "we" in found[0].message.lower()


def test_g4_03_allows_pronouns_in_fenced_code_blocks() -> None:
    """Fenced code blocks are example payloads — they may contain prose
    quotations that themselves use first-person plural without leaking
    orchestrator-voice into the agent's prompt."""
    rule = _rule("R.G4.03")
    ok = _CLEAN_FRONTMATTER + (
        "## A\n\nbacklog. Hand off to curator.\n\n"
        "## B\n\n```\nWe spend two hours every Monday on this.\n```\n\n"
        "## C\n\nstub.\n"
    )
    assert _violations_for(rule, ok) == []


def test_g4_03_allows_pronouns_in_inline_code() -> None:
    rule = _rule("R.G4.03")
    ok = _CLEAN_FRONTMATTER + (
        "## A\n\nbacklog. The alias `we_internal` is reserved. Hand off to curator.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    assert _violations_for(rule, ok) == []


def test_g4_03_allows_pronouns_in_html_comments() -> None:
    rule = _rule("R.G4.03")
    ok = _CLEAN_FRONTMATTER + (
        "## A\n\nbacklog. <!-- we know this is fine --> Hand off to curator.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    assert _violations_for(rule, ok) == []


# --------------------------------------------------------------------------- #
# R.G4.04 — build-fleet must cite an official UiPath skill
# --------------------------------------------------------------------------- #


_BUILD_FRONTMATTER = (
    "---\n"
    "name: forger-rpa\n"
    "description: stub\n"
    "tools: Read, Write\n"
    "model: sonnet\n"
    "fleet: build\n"
    "model_tier: mid_stakes\n"
    "---\n"
)


def test_g4_04_skipped_for_non_build_fleet() -> None:
    """Discovery / operate / meta agents are out of scope for R.G4.04."""
    rule = _rule("R.G4.04")
    assert _violations_for(rule, _CLEAN_AGENT) == []


def test_g4_04_clean_build_passes_with_skill_citation() -> None:
    rule = _rule("R.G4.04")
    ok = _BUILD_FRONTMATTER + (
        "## A\n\nUse uipath-rpa-workflows. Hand off to reviewer.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    assert _violations_for(rule, ok) == []


def test_g4_04_offender_caught() -> None:
    rule = _rule("R.G4.04")
    bad = _BUILD_FRONTMATTER + (
        "## A\n\nNo skill citation. Hand off to reviewer.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    found = _violations_for(rule, bad)
    assert len(found) == 1 and found[0].severity == "error"


# --------------------------------------------------------------------------- #
# R.G4.05 — operate-fleet must mention events.jsonl or sentry
# --------------------------------------------------------------------------- #


_OPERATE_FRONTMATTER = (
    "---\n"
    "name: surgeon\n"
    "description: stub\n"
    "tools: Read, Write\n"
    "model: sonnet\n"
    "fleet: operate\n"
    "model_tier: mid_stakes\n"
    "---\n"
)


def test_g4_05_skipped_for_non_operate_fleet() -> None:
    rule = _rule("R.G4.05")
    assert _violations_for(rule, _CLEAN_AGENT) == []


def test_g4_05_clean_operate_passes() -> None:
    rule = _rule("R.G4.05")
    ok = _OPERATE_FRONTMATTER + (
        "## A\n\nReads from events.jsonl. Hand off to conductor.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    assert _violations_for(rule, ok) == []


def test_g4_05_offender_caught() -> None:
    rule = _rule("R.G4.05")
    bad = _OPERATE_FRONTMATTER + (
        "## A\n\nDoes things. Hand off to conductor.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    found = _violations_for(rule, bad, path=SURGEON_PATH)
    assert len(found) == 1 and found[0].severity == "error"


# --------------------------------------------------------------------------- #
# R.G4.06 — discovery-fleet must mention backlog or candidate id
# --------------------------------------------------------------------------- #


def test_g4_06_skipped_for_non_discovery_fleet() -> None:
    rule = _rule("R.G4.06")
    bad_no_backlog_but_build = _BUILD_FRONTMATTER + (
        "## A\n\nUses uipath-rpa-workflows. Hand off to reviewer.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    assert _violations_for(rule, bad_no_backlog_but_build) == []


def test_g4_06_clean_passes_with_backlog() -> None:
    rule = _rule("R.G4.06")
    ok = _CLEAN_FRONTMATTER + (
        "## A\n\nReads the backlog. Hand off to curator.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    assert _violations_for(rule, ok) == []


def test_g4_06_clean_passes_with_candidate_id() -> None:
    """A literal ``C-12345`` token also satisfies the rule."""
    rule = _rule("R.G4.06")
    ok = _CLEAN_FRONTMATTER + (
        "## A\n\nUpdate C-12345 in storage. Hand off to curator.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    assert _violations_for(rule, ok) == []


def test_g4_06_offender_caught() -> None:
    rule = _rule("R.G4.06")
    bad = _CLEAN_FRONTMATTER + (
        "## A\n\nPolls. Hand off to curator.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    found = _violations_for(rule, bad)
    assert len(found) == 1 and found[0].severity == "error"


# --------------------------------------------------------------------------- #
# R.G4.07 — stop-condition phrase
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "phrase",
    ["Done when ready", "Stop when finished", "Completion criteria: x", "When the work is done", "Hand off to curator"],
)
def test_g4_07_each_phrase_satisfies(phrase: str) -> None:
    rule = _rule("R.G4.07")
    ok = _CLEAN_FRONTMATTER + (
        f"## A\n\nbacklog. {phrase}.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    assert _violations_for(rule, ok) == []


def test_g4_07_offender_caught() -> None:
    rule = _rule("R.G4.07")
    bad = _CLEAN_FRONTMATTER + (
        "## A\n\nbacklog. Just keep going forever.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    found = _violations_for(rule, bad)
    assert len(found) == 1 and found[0].severity == "error"


# --------------------------------------------------------------------------- #
# R.G4.08 — bare URLs must have a context noun within ±60 chars
# --------------------------------------------------------------------------- #


def test_g4_08_clean_with_context_passes() -> None:
    rule = _rule("R.G4.08")
    ok = _CLEAN_FRONTMATTER + (
        "## A\n\nbacklog. See the docs at https://example.com/api for help. Hand off to curator.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    assert _violations_for(rule, ok) == []


def test_g4_08_offender_caught() -> None:
    rule = _rule("R.G4.08")
    bad = _CLEAN_FRONTMATTER + (
        "## A\n\nbacklog. Visit https://example.com/api. Hand off to curator.\n\n"
        "## B\n\nstub.\n\n## C\n\nstub.\n"
    )
    found = _violations_for(rule, bad)
    assert len(found) == 1 and found[0].severity == "error"


def test_g4_08_ignores_urls_inside_fenced_code_blocks() -> None:
    rule = _rule("R.G4.08")
    ok = _CLEAN_FRONTMATTER + (
        "## A\n\nbacklog. Hand off to curator.\n\n"
        "## B\n\n```\nxmlns:bpmn=\"http://www.omg.org/spec/BPMN/20100524/MODEL\"\n```\n\n"
        "## C\n\nstub.\n"
    )
    assert _violations_for(rule, ok) == []


# --------------------------------------------------------------------------- #
# R.G4.09 — tools subset of canonical Claude Code tool set
# --------------------------------------------------------------------------- #


def test_g4_09_clean_passes() -> None:
    rule = _rule("R.G4.09")
    assert _violations_for(rule, _CLEAN_AGENT) == []


def test_g4_09_mcp_prefix_is_allowed() -> None:
    """``mcp__*`` tools are server-provided and must not be rejected."""
    rule = _rule("R.G4.09")
    ok = (
        "---\n"
        "name: scout\n"
        "description: stub\n"
        "tools: Read, mcp__playwright__browse, mcp__github__search\n"
        "model: haiku\n"
        "fleet: discovery\n"
        "model_tier: continuous\n"
        "---\n" + _CLEAN_BODY
    )
    assert _violations_for(rule, ok) == []


def test_g4_09_offender_caught() -> None:
    rule = _rule("R.G4.09")
    bad = (
        "---\n"
        "name: scout\n"
        "description: stub\n"
        "tools: Read, NotARealTool\n"
        "model: haiku\n"
        "fleet: discovery\n"
        "model_tier: continuous\n"
        "---\n" + _CLEAN_BODY
    )
    found = _violations_for(rule, bad)
    assert len(found) == 1 and found[0].severity == "error"


# --------------------------------------------------------------------------- #
# R.G4.10 — model_tier matches policy.yaml::routing.bindings
# --------------------------------------------------------------------------- #


def test_g4_10_clean_scout_passes() -> None:
    rule = _rule("R.G4.10")
    assert _violations_for(rule, _CLEAN_AGENT) == []


def test_g4_10_offender_caught() -> None:
    rule = _rule("R.G4.10")
    bad = (
        "---\n"
        "name: scout\n"
        "description: stub\n"
        "tools: Read, Bash\n"
        "model: haiku\n"
        "fleet: discovery\n"
        "model_tier: high_stakes\n"
        "---\n" + _CLEAN_BODY
    )
    found = _violations_for(rule, bad)
    assert len(found) == 1 and found[0].severity == "error"
    assert "high_stakes" in found[0].message
    assert "continuous" in found[0].message


def test_g4_10_unknown_agent_caught() -> None:
    rule = _rule("R.G4.10")
    bad = (
        "---\n"
        "name: scout\n"
        "description: stub\n"
        "tools: Read\n"
        "model: haiku\n"
        "fleet: discovery\n"
        "model_tier: continuous\n"
        "---\n" + _CLEAN_BODY
    )
    fake_path = rr.AGENTS_DIR / "ghost-agent.md"
    found = [v for v in rule.check(fake_path, bad) if v.rule_id == rule.id]
    assert len(found) == 1
    assert "no entry" in found[0].message


# --------------------------------------------------------------------------- #
# Violation contract sanity (pydantic v2 model)
# --------------------------------------------------------------------------- #


def test_violation_str_includes_severity_rule_and_agent() -> None:
    v = Violation(rule_id="R.G4.99", severity="error", agent="scout", line=42, message="boom")
    rendered = str(v)
    assert "R.G4.99" in rendered
    assert "ERROR" in rendered
    assert "scout" in rendered
    assert "42" in rendered


def test_violation_severity_literal_is_validated() -> None:
    with pytest.raises(Exception):
        Violation(rule_id="R.G4.99", severity="catastrophic", agent="scout", message="x")  # type: ignore[arg-type]
