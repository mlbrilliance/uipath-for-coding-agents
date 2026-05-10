"""Prompt-body invariants for AURORA's 19 agent definitions.

T-G2 — complements T-G1 (frontmatter schema) by validating the *markdown body*
of every agent file under ``agents/``. Five families of assertion run,
parametrised over the closed set of 19 agents:

1. ``test_no_banned_patterns_in_body`` — none of the contradicted-by-docs
   patterns from :mod:`tests.agents.banned_patterns` appear in the body.
2. ``test_cited_skills_exist_or_are_official_uipath`` — every backtick-quoted
   ``uipath-…`` / ``aurora-…`` citation resolves either to a local
   ``skills/<name>/SKILL.md`` or to the seven official UiPath skills.
3. ``test_cited_sibling_agents_exist`` — every backtick-quoted sibling agent
   name resolves to a real ``agents/<name>.md`` file (typo guard).
4. ``test_build_agent_names_correct_skill`` — Build agents cite the skill
   their picker-matrix row demands.
5. ``test_no_anthropic_api_key_anywhere`` — belt-and-braces sentinel that
   walks the whole ``agents/`` tree.

The body is everything *after* the YAML frontmatter (which T-G1 owns).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.agents.banned_patterns import (
    BANNED_REGEXES,
    BUILD_AGENT_SKILL_REQUIREMENTS,
    KNOWN_AGENTS,
    OFFICIAL_UIPATH_SKILLS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"
SKILLS_DIR = REPO_ROOT / "skills"


# Backtick-quoted skill citation (we only flag explicit references). A
# leading single backtick is required so plain-prose mentions of e.g. SDK
# package names do not collide with the skill allow-list.
SKILL_CITATION_RE = re.compile(r"`((?:uipath|aurora)-[a-z][a-z-]*)`")

# Backtick-quoted sibling-agent citation. Closed set of 19 — typos like
# `scoot` or `forger-foo` are caught by the whitelist below.
AGENT_NAME_PATTERN = (
    r"scout|curator|analyst|interviewer|strategist"
    r"|architect|cartographer|forger-(?:rpa|coded|agent|maestro)"
    r"|reviewer|tester"
    r"|sentry|diagnostician|surgeon|auditor|concierge"
    r"|conductor"
)
AGENT_CITATION_RE = re.compile(rf"`({AGENT_NAME_PATTERN})`")

# YAML frontmatter delimiter — body begins after the second `---` line.
FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def _load_agent_files() -> list[Path]:
    """Return the 19 agent definition files in stable name order."""
    files = sorted(AGENTS_DIR.glob("*.md"))
    if len(files) != 19:
        raise AssertionError(
            f"Expected 19 agent files under {AGENTS_DIR}, found {len(files)}: "
            f"{[f.name for f in files]}"
        )
    return files


def _strip_frontmatter(text: str) -> str:
    """Return everything after the YAML frontmatter block."""
    match = FRONTMATTER_RE.match(text)
    return text[match.end():] if match else text


def _agent_id(path: Path) -> str:
    return path.stem


AGENT_FILES = _load_agent_files()
AGENT_IDS = [_agent_id(p) for p in AGENT_FILES]


# --------------------------------------------------------------------------- #
# Test 1 - banned regexes (one parametrised case per agent x pattern pair)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "agent_path",
    AGENT_FILES,
    ids=AGENT_IDS,
)
@pytest.mark.parametrize(
    "pattern,rationale",
    BANNED_REGEXES,
    ids=[r.pattern for r, _ in BANNED_REGEXES],
)
def test_no_banned_patterns_in_body(
    agent_path: Path, pattern: re.Pattern[str], rationale: str
) -> None:
    body = _strip_frontmatter(agent_path.read_text(encoding="utf-8"))
    match = pattern.search(body)
    assert match is None, (
        f"{agent_path.relative_to(REPO_ROOT)}: matched banned pattern "
        f"{pattern.pattern!r} → {match.group(0)!r}\nRationale: {rationale}"
    )


# --------------------------------------------------------------------------- #
# Test 2 — backtick-cited skills must resolve
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_path", AGENT_FILES, ids=AGENT_IDS)
def test_cited_skills_exist_or_are_official_uipath(agent_path: Path) -> None:
    body = _strip_frontmatter(agent_path.read_text(encoding="utf-8"))
    citations = sorted(set(SKILL_CITATION_RE.findall(body)))
    missing: list[str] = []
    for name in citations:
        local = SKILLS_DIR / name / "SKILL.md"
        if local.is_file():
            continue
        if name in OFFICIAL_UIPATH_SKILLS:
            continue
        missing.append(name)
    assert not missing, (
        f"{agent_path.relative_to(REPO_ROOT)}: cites unknown skills "
        f"{missing}. Skills must exist at skills/<name>/SKILL.md or be one "
        f"of the seven official UiPath skills: "
        f"{sorted(OFFICIAL_UIPATH_SKILLS)}"
    )


# --------------------------------------------------------------------------- #
# Test 3 — backtick-cited sibling agents must resolve
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("agent_path", AGENT_FILES, ids=AGENT_IDS)
def test_cited_sibling_agents_exist(agent_path: Path) -> None:
    body = _strip_frontmatter(agent_path.read_text(encoding="utf-8"))
    citations = sorted(set(AGENT_CITATION_RE.findall(body)))
    missing: list[str] = []
    for name in citations:
        # The regex itself enforces the closed set, but double-check the
        # corresponding markdown file exists and the name is in KNOWN_AGENTS.
        if name not in KNOWN_AGENTS:
            missing.append(f"{name} (not in closed 19-agent set)")
            continue
        if not (AGENTS_DIR / f"{name}.md").is_file():
            missing.append(f"{name} (agents/{name}.md missing)")
    assert not missing, (
        f"{agent_path.relative_to(REPO_ROOT)}: cites unresolved sibling "
        f"agents {missing}"
    )


# --------------------------------------------------------------------------- #
# Test 4 — Build agents must cite their picker-matrix skill
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "agent_id,expected_skill",
    sorted(BUILD_AGENT_SKILL_REQUIREMENTS.items()),
    ids=sorted(BUILD_AGENT_SKILL_REQUIREMENTS.keys()),
)
def test_build_agent_names_correct_skill(
    agent_id: str, expected_skill: str
) -> None:
    agent_path = AGENTS_DIR / f"{agent_id}.md"
    assert agent_path.is_file(), f"missing agent file {agent_path}"
    body = _strip_frontmatter(agent_path.read_text(encoding="utf-8"))
    citations = set(SKILL_CITATION_RE.findall(body))
    assert expected_skill in citations, (
        f"{agent_path.relative_to(REPO_ROOT)}: Build-agent body must cite "
        f"skill `{expected_skill}` per CLAUDE.md picker matrix; cited skills "
        f"were {sorted(citations) or '(none)'}"
    )


# --------------------------------------------------------------------------- #
# Test 5 — belt-and-braces ANTHROPIC_API_KEY sweep across agents/
# --------------------------------------------------------------------------- #


def test_no_anthropic_api_key_anywhere() -> None:
    offenders: list[str] = []
    for path in AGENT_FILES:
        text = path.read_text(encoding="utf-8")
        if "ANTHROPIC_API_KEY" in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert not offenders, (
        f"ANTHROPIC_API_KEY referenced in: {offenders}. Claude is "
        f"subscription OAuth — never an API-key env var (CLAUDE.md "
        f"auth model)."
    )
