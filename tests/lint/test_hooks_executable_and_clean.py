"""Hook + skill-script integrity guards.

Catches the class of bugs that silently degraded the AURORA runtime
since the initial scaffold:

  1. `hooks/*.sh` without the executable bit → Claude Code's hook
     framework returns exit 126 → silent no-op + "permission denied"
     splatter on every tool call. (B1)
  2. `AURORA_HOME` defaulting to `/opt/aurora` (root-owned) → every
     hook's `mkdir` failed in user shells. (B2)
  3. Downstream skill scripts (`skills/aurora-*/scripts/*.py`) without
     the executable bit → some hooks gate on `[[ -x <path> ]]` and
     silently `exit 0` without invoking them. The gate is now `-f`
     (since the hooks call `python3 <path>` anyway) but we also keep
     the +x bit because direct-shellout call paths (systemd unit,
     manual debug) rely on it. (B3 + B4)
  4. Hook JQ paths that don't match Claude Code's actual PostToolUse
     event schema → the failure-classification branch never fires
     even when the hook runs. (B5) Real events use `.tool_response.
     isError`, `.tool_response.stderr` (Bash), `.tool_response.text`
     (text-shaped tools); the legacy `.result.success`/`.result.error`
     paths never matched. We test this by running the hook against
     frozen real-shaped fixtures.

These checks are intentionally lightweight (no LLM, no SDK) so they
live in `tests/lint/` and run as part of `make ci`.
"""
from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "hooks"
FIXTURES_DIR = REPO_ROOT / "tests" / "lint" / "fixtures" / "hooks"

HOOK_SCRIPTS = sorted(HOOKS_DIR.glob("*.sh"))

# Skill scripts the hooks (or aurora CLI / systemd unit) shell out to.
# These need the +x bit because at least one call path invokes them
# directly (e.g. systemd ExecStart).
EXPECTED_EXECUTABLE_SKILL_SCRIPTS = [
    REPO_ROOT / "skills" / "aurora-recall" / "scripts" / "recall.py",
    REPO_ROOT / "skills" / "aurora-fingerprint" / "scripts" / "cluster.py",
    REPO_ROOT / "skills" / "aurora-policy" / "scripts" / "validate_policy.py",
    REPO_ROOT / "skills" / "aurora-auth" / "scripts" / "mint_token.py",
]


@pytest.mark.parametrize("path", HOOK_SCRIPTS, ids=lambda p: p.name)
def test_hook_script_is_executable(path: Path) -> None:
    """Every `hooks/*.sh` must be +x or Claude Code's hook framework
    rejects it with exit 126 (permission denied) on every tool call."""
    assert path.exists(), f"hook missing: {path}"
    mode = path.stat().st_mode
    assert mode & stat.S_IXUSR, (
        f"hook is not executable (chmod +x missing): {path.relative_to(REPO_ROOT)}"
    )


@pytest.mark.parametrize(
    "path", EXPECTED_EXECUTABLE_SKILL_SCRIPTS, ids=lambda p: p.name
)
def test_skill_script_is_executable(path: Path) -> None:
    """Skill scripts that hooks (and systemd unit) invoke must be +x."""
    assert path.exists(), f"skill script missing: {path}"
    mode = path.stat().st_mode
    assert mode & stat.S_IXUSR, (
        f"skill script is not executable (chmod +x missing): "
        f"{path.relative_to(REPO_ROOT)}"
    )


@pytest.mark.parametrize("path", HOOK_SCRIPTS, ids=lambda p: p.name)
def test_hook_runs_clean_in_minimal_env(path: Path) -> None:
    """In a stripped environment (no AURORA_HOME, no `.env`), every
    hook must exit 0 with empty stderr when fed a realistic event.

    This is the reproducer for the silent-degradation bug where the
    `/opt/aurora` default and the missing +x bit caused
    `mkdir: cannot create '/opt/aurora': Permission denied` to splatter
    on every tool call.

    We use a tmp `HOME` and `CLAUDE_PROJECT_DIR` so the hook's defaults
    actually fire (and we can assert the writable-default invariant).
    """
    minimal_env = {
        "HOME": os.environ["HOME"],
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
    }
    fake_event = (
        '{"tool_name":"Bash","tool_input":{"command":"echo probe"},'
        '"tool_response":{"stdout":"probe\\n","stderr":"","exit_code":0}}'
    )
    result = subprocess.run(
        ["bash", str(path)],
        input=fake_event,
        env=minimal_env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, (
        f"hook {path.name} exited {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert result.stderr == "", (
        f"hook {path.name} emitted stderr in a clean env "
        f"(this is the regression-guard for the /opt/aurora + missing-+x "
        f"bug that silently degraded every tool call):\n{result.stderr}"
    )


# --------------------------------------------------------------------------- #
# B5 regression: post-tool-fingerprint.sh must parse Claude Code's REAL
# PostToolUse event schema (.tool_response.isError, .tool_response.stderr,
# .tool_response.text), not the fictional `.result.*` schema we shipped
# initially.
# --------------------------------------------------------------------------- #


def _run_post_tool_hook(payload_path: Path, *, aurora_home: Path) -> None:
    """Pipe a fixture into hooks/post-tool-fingerprint.sh.

    Uses a tmp AURORA_HOME so each test owns its events.jsonl /
    fingerprints.db / hooks.log without polluting the user's state.
    """
    env = {
        "HOME": os.environ["HOME"],
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
        "AURORA_HOME": str(aurora_home),
    }
    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "post-tool-fingerprint.sh")],
        input=payload_path.read_text(),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, (
        f"hook exited {result.returncode}; stderr={result.stderr!r}"
    )


def test_real_bash_success_payload_does_not_fingerprint(tmp_path: Path) -> None:
    """A successful Bash tool_response (isError=false) must NOT write
    to events.jsonl and must NOT create fingerprints.db."""
    _run_post_tool_hook(
        FIXTURES_DIR / "posttooluse_bash_success.json",
        aurora_home=tmp_path,
    )
    assert not (tmp_path / "events.jsonl").exists(), (
        "Bash success caused a tool_failed event — JQ schema mismatch"
    )
    assert not (tmp_path / "fingerprints.db").exists(), (
        "Bash success triggered fingerprint clustering"
    )


def test_real_bash_failure_payload_writes_event_and_fingerprint(
    tmp_path: Path,
) -> None:
    """A real Bash failure payload (isError=true with stderr containing a
    SelectorNotFoundException) must:
        1. Append a kind=tool_failed event to events.jsonl.
        2. Shell out to skills/aurora-fingerprint/scripts/cluster.py.
        3. Land a row in fingerprints.db classified as
           kind='selector-broken', refinement='aaname-mismatch'.
    """
    _run_post_tool_hook(
        FIXTURES_DIR / "posttooluse_bash_failure.json",
        aurora_home=tmp_path,
    )

    events_path = tmp_path / "events.jsonl"
    assert events_path.exists(), (
        "events.jsonl was not written — failure-classification branch "
        "of the hook did not fire on a real CC isError=true payload"
    )
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line]
    assert len(events) == 1
    assert events[0]["kind"] == "tool_failed"
    assert "SelectorNotFound" in events[0]["details"]["message"]

    fingerprints = tmp_path / "fingerprints.db"
    assert fingerprints.exists(), (
        "fingerprints.db not created — cluster.py shellout did not run"
    )
    rows = sqlite3.connect(str(fingerprints)).execute(
        "SELECT kind, refinement FROM fingerprints"
    ).fetchall()
    assert rows, "fingerprints.db has no rows"
    kinds = {r[0] for r in rows}
    refinements = {r[1] for r in rows}
    assert "selector-broken" in kinds, (
        f"selector classification missed; kinds={kinds}"
    )
    assert "aaname-mismatch" in refinements, (
        f"aaname refinement missed; refinements={refinements}"
    )


def test_real_edit_failure_payload_writes_event(tmp_path: Path) -> None:
    """Text-shaped tool failure (.tool_response.text + isError=true) —
    Edit, Read, Write all use this shape — must also fingerprint."""
    _run_post_tool_hook(
        FIXTURES_DIR / "posttooluse_edit_failure.json",
        aurora_home=tmp_path,
    )
    events_path = tmp_path / "events.jsonl"
    assert events_path.exists(), (
        "Text-shaped tool_response.text+isError=true did not produce a "
        "tool_failed event"
    )
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line]
    assert len(events) == 1
    assert events[0]["scope"]["tool"] == "Edit"
    assert "file not found" in events[0]["details"]["message"]
    assert (tmp_path / "fingerprints.db").exists()
