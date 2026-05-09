"""Banned patterns and required-skill mappings for agent prompt-body invariants.

These collections drive ``tests/agents/test_prompt_invariants.py``. Each entry
in :data:`BANNED_REGEXES` is a ``(compiled_regex, rationale)`` tuple — the
rationale is surfaced in failure messages so the offending agent prose can be
patched without having to re-derive *why* the pattern is banned.

The list grows as the grill artifact (``docs/grill-2026-05-09.md``) and any
follow-on retros surface contradictions between agent definitions and what
the UiPath docs actually support.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Banned patterns — every entry is justified by a contradicted-by-docs verdict
# in docs/grill-2026-05-09.md or by an explicit AURORA convention rule.
# --------------------------------------------------------------------------- #

BANNED_REGEXES: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"ANTHROPIC_API_KEY"),
        "no Anthropic API key — Claude is subscription OAuth via "
        "~/.claude/credentials.json (see CLAUDE.md auth model)",
    ),
    (
        re.compile(r"\buip\b"),
        "fictional `uip` CLI was renamed to `uipath` in T-A1; the official "
        "CLI shipped by uipath-python is `uipath`",
    ),
    (
        re.compile(r"<uipath:taskBinding"),
        "BPMN `<uipath:taskBinding>` extension stripped in T-A2 — bindings "
        "now live in bindings.json (the only documented source of truth)",
    ),
    (
        re.compile(
            r"publish.*test set.*Test Manager.*via API"
            r"|directly publishes? test set.*Test Manager"
            r"|publish(?:es)?\s+(?:the\s+)?test set to Test Manager"
            r"|--target test-manager"
        ),
        "Tester flow corrected in T-E1: Studio publish → Orchestrator → "
        "Test Manager link. There is no documented Test Manager `publish "
        "test set` API endpoint (see docs/grill-2026-05-09.md §Contradicted #5)",
    ),
]


# --------------------------------------------------------------------------- #
# Build-agent → expected skill citation. Sourced from CLAUDE.md's
# "When to use which skill" picker matrix. Build agents must cite the
# matching official UiPath skill in their prompt body so Architect's
# pattern-selection contract is enforceable.
# --------------------------------------------------------------------------- #

BUILD_AGENT_SKILL_REQUIREMENTS: dict[str, str] = {
    "forger-rpa": "uipath-rpa-workflows",
    "forger-coded": "uipath-coded-workflows",
    "forger-agent": "uipath-coded-agents",
    "forger-maestro": "uipath-platform",
}


# --------------------------------------------------------------------------- #
# Official UiPath skill allow-list — the seven entries on
# https://github.com/UiPath/skills (codified in CLAUDE.md). R.SW.06.1
# locks this set: no aliases, no SDK package names, no shorthand.
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Closed set of 19 sibling agents. Used to detect typos in cross-agent
# citations (e.g. "scoot" instead of "scout", "forger-foo" instead of a
# real Forger).
# --------------------------------------------------------------------------- #

KNOWN_AGENTS: frozenset[str] = frozenset(
    {
        # Discovery
        "scout",
        "curator",
        "analyst",
        "interviewer",
        "strategist",
        # Build
        "architect",
        "cartographer",
        "forger-rpa",
        "forger-coded",
        "forger-agent",
        "forger-maestro",
        "reviewer",
        "tester",
        # Operate
        "sentry",
        "diagnostician",
        "surgeon",
        "auditor",
        "concierge",
        # Meta
        "conductor",
    }
)
