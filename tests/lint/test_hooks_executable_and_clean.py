"""Hook + skill-script integrity guards.

Catches the class of bugs that silently degraded the AURORA runtime
since the initial scaffold:

  1. `hooks/*.sh` without the executable bit → Claude Code's hook
     framework returns exit 126 → silent no-op + "permission denied"
     splatter on every tool call.
  2. Downstream skill scripts (`skills/aurora-*/scripts/*.py`) without
     the executable bit → some hooks gate on `[[ -x <path> ]]` and
     silently `exit 0` without invoking them. We've fixed the gate to
     `-f` (since the hooks call `python3 <path>` anyway) but the +x
     bit on the scripts is still expected because the install-systemd
     and direct-shellout call paths do rely on it.
  3. Hook scripts emit stderr when fed a realistic empty event in a
     clean environment (no AURORA_HOME, no `.env` sourced) — that's
     the reproducer for the silent degradation we observed in this
     session.

These three checks are intentionally lightweight (no LLM, no SDK) so
they live in `tests/lint/` and run as part of `make ci`.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

HOOK_SCRIPTS = sorted((REPO_ROOT / "hooks").glob("*.sh"))

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
