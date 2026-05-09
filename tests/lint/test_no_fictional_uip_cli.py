"""Asserts the working tree no longer references a fictional `uip` CLI.

The real CLI is `uipath` (shipped by uipath-python). The string `uip` standing
alone should appear ONLY in historical / narrative documents that describe the
rename. New code, agents, skills, policy, scripts, and settings must use
`uipath`.

Acceptance test for T-A1.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Files that legitimately reference `uip` as historical narrative.
EXCLUDED_PATHS = {
    "docs/grill-2026-05-09.md",
    "tasks.md",
    "PDD.md",
    "tests/lint/test_no_fictional_uip_cli.py",
}

EXCLUDED_DIRS = {".git", ".venv", "local_cache", ".pytest_cache", "node_modules"}

UIP_WORD = re.compile(r"\buip\b")


def _walk_tracked_files() -> list[Path]:
    """Use git to enumerate tracked files; falls back to a Path glob."""
    try:
        out = subprocess.check_output(
            ["git", "ls-files"], cwd=REPO_ROOT, text=True
        )
        return [REPO_ROOT / line for line in out.splitlines() if line]
    except Exception:
        return [
            p
            for p in REPO_ROOT.rglob("*")
            if p.is_file()
            and not any(part in EXCLUDED_DIRS for part in p.parts)
        ]


def test_no_fictional_uip_cli_in_operational_files() -> None:
    offenders: list[tuple[str, int, str]] = []
    for path in _walk_tracked_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in EXCLUDED_PATHS:
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if UIP_WORD.search(line):
                offenders.append((rel, lineno, line.strip()[:200]))
    assert not offenders, "Found fictional `uip` references:\n" + "\n".join(
        f"  {r}:{n}: {ln}" for r, n, ln in offenders
    )


def test_lint_excludes_are_real_files() -> None:
    """Sanity check: the excluded paths must exist (else the exclude is dead)."""
    for rel in EXCLUDED_PATHS:
        if rel == "tests/lint/test_no_fictional_uip_cli.py":
            continue  # the test file always exists by definition
        assert (REPO_ROOT / rel).exists(), f"excluded path missing: {rel}"


def test_lint_catches_a_synthetic_offender(tmp_path: Path, monkeypatch) -> None:
    """Prove the regex enforcement is real by feeding it a synthetic offender."""
    offender = tmp_path / "synthetic.md"
    offender.write_text("install via `uip skills install` first\n")
    text = offender.read_text()
    matches = list(UIP_WORD.finditer(text))
    assert matches, "regex failed to match a known offending line"


def test_lint_does_not_catch_uipath() -> None:
    """The rename target `uipath` must not match the fictional-binary regex."""
    assert not UIP_WORD.search("uipath publish")
    assert not UIP_WORD.search("uipath-python")
    assert not UIP_WORD.search("docs.uipath.com")
    assert not UIP_WORD.search("uipath.json")
