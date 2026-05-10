"""T-G4 — Reviewer-style heuristic lint over ``agents/<name>.md``.

The Reviewer agent (`agents/reviewer.md`) applies senior-RPA-developer
review heuristics to anything Forger sub-agents produce. T-G2 already
codifies banned phrases and skill-citation correctness; T-G1 owns the
frontmatter schema. This module fills the remaining gap — the
Reviewer-voice heuristics that catch prompt-body drift.

Every rule is a pure ``(agent_path, agent_text) -> list[Violation]``
function. Synthetic offenders prove each rule actually fires (R.T.04 —
error-path tests are mandatory).

Scope: offline, deterministic, no LLM calls — same pattern as T-G1/T-G2.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tests.agents.contracts.violation import Violation

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"
POLICY_PATH = REPO_ROOT / "policy.yaml"


# --------------------------------------------------------------------------- #
# Body-vs-frontmatter splitting + helpers for stripping noise
# --------------------------------------------------------------------------- #

_FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<fm>.*?)\n---\s*\n(?P<body>.*)\Z", re.DOTALL)
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _split(path: Path, text: str) -> tuple[dict[str, Any], str, int]:
    """Return ``(frontmatter, body, body_offset_lines)`` for an agent file.

    ``body_offset_lines`` is the 1-based line index in the raw file where
    the body starts, so violation line numbers stay anchored to the
    original markdown source.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text, 1
    fm_data = yaml.safe_load(match.group("fm")) or {}
    if not isinstance(fm_data, dict):
        fm_data = {}
    body = match.group("body")
    fm_lines = match.group("fm").count("\n") + 1
    body_offset = 1 + fm_lines + 2
    return fm_data, body, body_offset


def _strip_code_and_comments(text: str) -> str:
    """Replace fenced code blocks, inline code, and HTML comments with
    blank space (preserving newlines so line numbers don't drift)."""

    def _blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    text = _FENCED_CODE_RE.sub(_blank, text)
    text = _HTML_COMMENT_RE.sub(_blank, text)
    text = _INLINE_CODE_RE.sub(_blank, text)
    return text


def _line_of(body: str, body_offset: int, char_index: int) -> int:
    return body_offset + body[:char_index].count("\n")


# --------------------------------------------------------------------------- #
# ReviewerRule — every rule registers as one of these
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReviewerRule:
    id: str
    description: str
    severity: str
    check: Callable[[Path, str], list[Violation]]
    synthetic_offender: str

    def synthetic_offender_caught(self) -> bool:
        """Run the rule against its synthetic offender. Each rule must
        emit at least one violation at its declared severity."""
        path = AGENTS_DIR / "scout.md"
        violations = self.check(path, self.synthetic_offender)
        return any(v.rule_id == self.id and v.severity == self.severity for v in violations)


# --------------------------------------------------------------------------- #
# Constants reused by multiple rules
# --------------------------------------------------------------------------- #

CANONICAL_TOOLS: frozenset[str] = frozenset(
    {
        "Read",
        "Write",
        "Edit",
        "Bash",
        "Glob",
        "Grep",
        "Task",
        "WebFetch",
        "WebSearch",
        "NotebookEdit",
    }
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

STOP_CONDITION_PHRASES: tuple[str, ...] = (
    "Done when",
    "Stop when",
    "Completion criteria",
    "When the work is done",
    "Hand off to",
)

URL_CONTEXT_NOUNS: tuple[str, ...] = (
    "docs",
    "reference",
    "guide",
    "repo",
    "github",
    "issue",
    "tracker",
    "dashboard",
    "endpoint",
)

PRONOUN_RE = re.compile(r"\b(we|us|our)\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s)>\"'`]+")


def _agent_name(path: Path) -> str:
    return path.stem


def _load_policy() -> dict[str, Any]:
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8")) or {}


# --------------------------------------------------------------------------- #
# Individual rule implementations
# --------------------------------------------------------------------------- #


def rule_g4_01_frontmatter_present(path: Path, text: str) -> list[Violation]:
    """R.G4.01 — file has a parseable YAML frontmatter block (T-G1 owns
    schema validation; this rule only confirms shape)."""
    if not _FRONTMATTER_RE.match(text):
        return [
            Violation(
                rule_id="R.G4.01",
                severity="error",
                agent=_agent_name(path),
                line=1,
                message="agent file missing YAML frontmatter (--- ... ---)",
            )
        ]
    fm, _, _ = _split(path, text)
    if not fm:
        return [
            Violation(
                rule_id="R.G4.01",
                severity="error",
                agent=_agent_name(path),
                line=1,
                message="frontmatter is empty or not a YAML mapping",
            )
        ]
    return []


def rule_g4_02_three_sections(path: Path, text: str) -> list[Violation]:
    """R.G4.02 — body has at least three ``## `` headers."""
    _, body, _ = _split(path, text)
    cleaned = _strip_code_and_comments(body)
    headers = [
        line
        for line in cleaned.splitlines()
        if line.lstrip().startswith("## ") and not line.lstrip().startswith("### ")
    ]
    if len(headers) < 3:
        return [
            Violation(
                rule_id="R.G4.02",
                severity="error",
                agent=_agent_name(path),
                line=None,
                message=(
                    f"prompt body has only {len(headers)} ## section(s); "
                    "Reviewer expects at least 3 — a one-paragraph agent prompt "
                    "is a red flag"
                ),
            )
        ]
    return []


def rule_g4_03_no_first_person_plural(path: Path, text: str) -> list[Violation]:
    """R.G4.03 — no ``we``/``us``/``our`` in agent-prose body. Allowed
    inside fenced code blocks, inline code spans, and HTML comments."""
    _, body, body_offset = _split(path, text)
    cleaned = _strip_code_and_comments(body)
    violations: list[Violation] = []
    for match in PRONOUN_RE.finditer(cleaned):
        line_no = _line_of(body, body_offset, match.start())
        violations.append(
            Violation(
                rule_id="R.G4.03",
                severity="error",
                agent=_agent_name(path),
                line=line_no,
                message=(
                    f"first-person plural pronoun {match.group(0)!r} leaks "
                    "orchestrator-voice; address THIS agent in second person"
                ),
            )
        )
    return violations


def rule_g4_04_build_cites_official_skill(path: Path, text: str) -> list[Violation]:
    """R.G4.04 — Build-fleet agents must mention at least one official
    UiPath skill (R.SW.06.1)."""
    fm, body, _ = _split(path, text)
    if fm.get("fleet") != "build":
        return []
    cleaned_body = body
    if not any(skill in cleaned_body for skill in OFFICIAL_UIPATH_SKILLS):
        return [
            Violation(
                rule_id="R.G4.04",
                severity="error",
                agent=_agent_name(path),
                line=None,
                message=(
                    "Build-fleet agent body must cite at least one official "
                    f"UiPath skill (R.SW.06.1): {sorted(OFFICIAL_UIPATH_SKILLS)}"
                ),
            )
        ]
    return []


def rule_g4_05_operate_mentions_event_stream(path: Path, text: str) -> list[Violation]:
    """R.G4.05 — Operate-fleet agents must mention ``events.jsonl`` or
    ``sentry`` (case-insensitive). They share the same event stream."""
    fm, body, _ = _split(path, text)
    if fm.get("fleet") != "operate":
        return []
    haystack = body.lower()
    if "events.jsonl" in haystack or "sentry" in haystack:
        return []
    return [
        Violation(
            rule_id="R.G4.05",
            severity="error",
            agent=_agent_name(path),
            line=None,
            message=(
                "Operate-fleet agent body must mention `events.jsonl` or "
                "`sentry` — they share the same Sentry-emitted event stream"
            ),
        )
    ]


_CANDIDATE_ID_RE = re.compile(r"\bC-\d+\b")


def rule_g4_06_discovery_mentions_backlog(path: Path, text: str) -> list[Violation]:
    """R.G4.06 — Discovery-fleet agents must mention ``backlog`` or a
    candidate id of the form ``C-<digits>``."""
    fm, body, _ = _split(path, text)
    if fm.get("fleet") != "discovery":
        return []
    if "backlog" in body.lower() or _CANDIDATE_ID_RE.search(body):
        return []
    return [
        Violation(
            rule_id="R.G4.06",
            severity="error",
            agent=_agent_name(path),
            line=None,
            message=(
                "Discovery-fleet agent body must mention `backlog` or a "
                "candidate id matching `C-[0-9]+`"
            ),
        )
    ]


def rule_g4_07_stop_condition(path: Path, text: str) -> list[Violation]:
    """R.G4.07 — body contains a stop-condition phrase, catching the
    "agent runs forever" anti-pattern."""
    _, body, _ = _split(path, text)
    if any(phrase in body for phrase in STOP_CONDITION_PHRASES):
        return []
    return [
        Violation(
            rule_id="R.G4.07",
            severity="error",
            agent=_agent_name(path),
            line=None,
            message=(
                "agent body lacks a stop-condition phrase — expected one of "
                f"{list(STOP_CONDITION_PHRASES)} so the agent knows when it is done"
            ),
        )
    ]


def rule_g4_08_url_context(path: Path, text: str) -> list[Violation]:
    """R.G4.08 — bare ``http(s)://`` URLs in prose must have a context
    noun within ±60 chars. Skips code blocks, inline code, and HTML
    comments. ``mailto:`` and ``git@`` are out of scope by construction."""
    _, body, body_offset = _split(path, text)
    cleaned = _strip_code_and_comments(body)
    violations: list[Violation] = []
    for match in URL_RE.finditer(cleaned):
        start = max(0, match.start() - 60)
        end = min(len(cleaned), match.end() + 60)
        window = cleaned[start:end].lower()
        if any(noun in window for noun in URL_CONTEXT_NOUNS):
            continue
        line_no = _line_of(body, body_offset, match.start())
        violations.append(
            Violation(
                rule_id="R.G4.08",
                severity="error",
                agent=_agent_name(path),
                line=line_no,
                message=(
                    f"URL {match.group(0)!r} appears without a context noun "
                    f"within ±60 chars (one of {list(URL_CONTEXT_NOUNS)})"
                ),
            )
        )
    return violations


_TOOLS_FIELD_RE = re.compile(r"^tools:\s*(.+)$", re.MULTILINE)


def rule_g4_09_tools_subset(path: Path, text: str) -> list[Violation]:
    """R.G4.09 — every entry in the ``tools:`` frontmatter field is a
    canonical Claude Code tool or an ``mcp__*`` server tool."""
    fm, _, _ = _split(path, text)
    raw = fm.get("tools")
    if raw is None:
        return [
            Violation(
                rule_id="R.G4.09",
                severity="error",
                agent=_agent_name(path),
                line=None,
                message="frontmatter is missing required `tools` field",
            )
        ]
    if isinstance(raw, list):
        names = [str(x).strip() for x in raw]
    else:
        names = [t.strip() for t in str(raw).split(",")]
    violations: list[Violation] = []
    for name in names:
        if not name:
            continue
        if name in CANONICAL_TOOLS:
            continue
        if name.startswith("mcp__"):
            continue
        violations.append(
            Violation(
                rule_id="R.G4.09",
                severity="error",
                agent=_agent_name(path),
                line=None,
                message=(
                    f"tool {name!r} is not in the canonical Claude Code tool "
                    f"set {sorted(CANONICAL_TOOLS)} and is not an mcp__* server"
                ),
            )
        )
    return violations


def rule_g4_10_model_tier_matches_policy(path: Path, text: str) -> list[Violation]:
    """R.G4.10 — frontmatter ``model_tier`` matches
    ``policy.yaml::routing.bindings.<agent_name>``."""
    fm, _, _ = _split(path, text)
    declared = fm.get("model_tier")
    name = _agent_name(path)
    policy = _load_policy()
    bindings = (policy.get("routing") or {}).get("bindings") or {}
    expected = bindings.get(name)
    if expected is None:
        return [
            Violation(
                rule_id="R.G4.10",
                severity="error",
                agent=name,
                line=None,
                message=(
                    f"agent {name!r} has no entry in "
                    "policy.yaml::routing.bindings"
                ),
            )
        ]
    if declared != expected:
        return [
            Violation(
                rule_id="R.G4.10",
                severity="error",
                agent=name,
                line=None,
                message=(
                    f"model_tier mismatch: agent declares {declared!r}, "
                    f"policy.yaml routing.bindings.{name} is {expected!r}"
                ),
            )
        ]
    return []


# --------------------------------------------------------------------------- #
# Synthetic offenders — one per rule
# --------------------------------------------------------------------------- #

_OK_FRONTMATTER = (
    "---\n"
    "name: scout\n"
    "description: stub\n"
    "tools: Read, Bash, Glob, Grep\n"
    "model: haiku\n"
    "fleet: discovery\n"
    "model_tier: continuous\n"
    "---\n"
)

_OK_BODY = (
    "## Inputs\n\n- a\n\n"
    "## What you do\n\nbacklog item — Hand off to curator.\n\n"
    "## Output\n\nDone when emitted.\n"
)

OFFENDER_G4_01 = "no frontmatter at all\n\n" + _OK_BODY

OFFENDER_G4_02 = _OK_FRONTMATTER + "Single paragraph, no headers, totally flat. backlog. Hand off to curator.\n"

OFFENDER_G4_03 = (
    _OK_FRONTMATTER
    + "## A\n\nWe should automate this. backlog. Hand off to curator.\n\n"
    + "## B\n\nstub.\n\n## C\n\nstub.\n"
)

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

OFFENDER_G4_04 = (
    _BUILD_FRONTMATTER
    + "## A\n\nNo skill citation here at all. Hand off to reviewer.\n\n"
    + "## B\n\nstub.\n\n## C\n\nstub.\n"
)

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

OFFENDER_G4_05 = (
    _OPERATE_FRONTMATTER
    + "## A\n\nNo event stream reference. Hand off to conductor.\n\n"
    + "## B\n\nstub.\n\n## C\n\nstub.\n"
)

OFFENDER_G4_06 = (
    _OK_FRONTMATTER
    + "## A\n\nNo b@cklog mention here. Hand off to curator.\n\n"
    + "## B\n\nstub.\n\n## C\n\nstub.\n"
)

OFFENDER_G4_07 = (
    _OK_FRONTMATTER
    + "## A\n\nbacklog mention.\n\n"
    + "## B\n\nstub.\n\n## C\n\nstub.\n"
)

OFFENDER_G4_08 = (
    _OK_FRONTMATTER
    + "## A\n\nVisit https://example.com/api here without context. backlog. Hand off to curator.\n\n"
    + "## B\n\nstub.\n\n## C\n\nstub.\n"
)

OFFENDER_G4_09 = (
    "---\n"
    "name: scout\n"
    "description: stub\n"
    "tools: Read, NotARealTool\n"
    "model: haiku\n"
    "fleet: discovery\n"
    "model_tier: continuous\n"
    "---\n"
    + _OK_BODY
)

OFFENDER_G4_10 = (
    "---\n"
    "name: scout\n"
    "description: stub\n"
    "tools: Read, Bash\n"
    "model: haiku\n"
    "fleet: discovery\n"
    "model_tier: high_stakes\n"
    "---\n"
    + _OK_BODY
)


# --------------------------------------------------------------------------- #
# Registry + driver
# --------------------------------------------------------------------------- #

REVIEWER_RULES: list[ReviewerRule] = [
    ReviewerRule(
        id="R.G4.01",
        description="frontmatter present",
        severity="error",
        check=rule_g4_01_frontmatter_present,
        synthetic_offender=OFFENDER_G4_01,
    ),
    ReviewerRule(
        id="R.G4.02",
        description="body has >= 3 ## sections",
        severity="error",
        check=rule_g4_02_three_sections,
        synthetic_offender=OFFENDER_G4_02,
    ),
    ReviewerRule(
        id="R.G4.03",
        description="no first-person plural pronouns",
        severity="error",
        check=rule_g4_03_no_first_person_plural,
        synthetic_offender=OFFENDER_G4_03,
    ),
    ReviewerRule(
        id="R.G4.04",
        description="build-fleet cites official UiPath skill",
        severity="error",
        check=rule_g4_04_build_cites_official_skill,
        synthetic_offender=OFFENDER_G4_04,
    ),
    ReviewerRule(
        id="R.G4.05",
        description="operate-fleet mentions events.jsonl or sentry",
        severity="error",
        check=rule_g4_05_operate_mentions_event_stream,
        synthetic_offender=OFFENDER_G4_05,
    ),
    ReviewerRule(
        id="R.G4.06",
        description="discovery-fleet mentions backlog or candidate id",
        severity="error",
        check=rule_g4_06_discovery_mentions_backlog,
        synthetic_offender=OFFENDER_G4_06,
    ),
    ReviewerRule(
        id="R.G4.07",
        description="stop condition phrase present",
        severity="error",
        check=rule_g4_07_stop_condition,
        synthetic_offender=OFFENDER_G4_07,
    ),
    ReviewerRule(
        id="R.G4.08",
        description="bare URLs have surrounding context noun",
        severity="error",
        check=rule_g4_08_url_context,
        synthetic_offender=OFFENDER_G4_08,
    ),
    ReviewerRule(
        id="R.G4.09",
        description="tools is subset of canonical Claude Code tool set",
        severity="error",
        check=rule_g4_09_tools_subset,
        synthetic_offender=OFFENDER_G4_09,
    ),
    ReviewerRule(
        id="R.G4.10",
        description="model_tier matches policy.yaml::routing.bindings",
        severity="error",
        check=rule_g4_10_model_tier_matches_policy,
        synthetic_offender=OFFENDER_G4_10,
    ),
]


def lint_agent_file(path: Path) -> list[Violation]:
    """Run every registered rule against ``path``. Pure / offline."""
    text = path.read_text(encoding="utf-8")
    violations: list[Violation] = []
    for rule in REVIEWER_RULES:
        violations.extend(rule.check(path, text))
    return violations


__all__ = [
    "REVIEWER_RULES",
    "ReviewerRule",
    "Violation",
    "lint_agent_file",
]
