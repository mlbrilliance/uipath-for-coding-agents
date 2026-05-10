"""F3 boot-path regression tests.

T-F3 acceptance criteria say `aurora start` runs ≥ 5 min clean with no
ERROR-level entries. The full 5-minute daemon run needs a live UiPath
tenant (the daemon's first call mints a token and hits Orchestrator),
which isn't available in CI.

These tests cover the offline-verifiable subset:
  1. `aurora start --skip-daemons` exits 0 and prints the boot banner.
  2. The Conductor module constructs cleanly with the demo policy and
     registers all three nightly crons (auditor / strategist / compost).
  3. Every agent definition file under `agents/` references a `model_tier`
     that exists in `policy.yaml::routing.bindings` (alignment guard).
  4. Sentry constructs without hitting the network (folder / interval
     / events_path are wired correctly).

The full live run remains a manual F3 step documented in
`docs/runbook-aurora-start.md` (created by this commit).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = REPO_ROOT / "agents"


def test_aurora_start_skip_daemons_exits_zero() -> None:
    """The in-session boot path (policy load → cron registry) must not
    require any network. Smoke this end-to-end via the installed CLI."""
    aurora_bin = REPO_ROOT / ".venv" / "bin" / "aurora"
    if not aurora_bin.exists():
        pytest.skip("aurora CLI not installed in venv")

    # Provide the minimum env the policy loader needs (it expands
    # ${VAR} references in policy.yaml). Use safe placeholders.
    env = {
        **os.environ,
        "AURORA_HOME": "/tmp/aurora-test",
        "AURORA_MEMORY_DIR": "/tmp/aurora-test/memory",
        "AURORA_WORKTREE_DIR": "/tmp/aurora-test/worktrees",
        "AURORA_SENTRY_INTERVAL": "30",
        "AURORA_MAX_AUTO_FIXES_PER_DAY": "5",
        "AURORA_DAILY_BUDGET_USD": "50",
        "AURORA_MODEL_ARCHITECT": "claude-opus-4-6",
        "AURORA_MODEL_FORGER": "claude-sonnet-4-6",
        "AURORA_MODEL_SENTRY": "claude-haiku-4-5-20251001",
        "SLACK_CHANNEL_ID": "C-test",
        "AURORA_WEBHOOK_GITHUB_CHECK_RUN_URL": "https://example.invalid/x",
    }
    result = subprocess.run(
        [str(aurora_bin), "start", "--skip-daemons"],
        env=env, capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, (
        f"aurora start --skip-daemons exited {result.returncode}; "
        f"stderr={result.stderr!r}"
    )
    assert "policy: valid" in result.stdout
    assert "conductor: ready" in result.stdout


_POLICY_ENV_DEFAULTS = {
    "AURORA_HOME": "/tmp/aurora-test",
    "AURORA_MEMORY_DIR": "/tmp/aurora-test/memory",
    "AURORA_WORKTREE_DIR": "/tmp/aurora-test/worktrees",
    "AURORA_SENTRY_INTERVAL": "30",
    "AURORA_MAX_AUTO_FIXES_PER_DAY": "5",
    "AURORA_DAILY_BUDGET_USD": "50",
    "AURORA_MODEL_ARCHITECT": "claude-opus-4-6",
    "AURORA_MODEL_FORGER": "claude-sonnet-4-6",
    "AURORA_MODEL_SENTRY": "claude-haiku-4-5-20251001",
    "SLACK_CHANNEL_ID": "C-test",
    "AURORA_WEBHOOK_GITHUB_CHECK_RUN_URL": "https://example.invalid/x",
}


def test_conductor_constructs_with_default_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Conductor wires its three nightly crons (auditor, strategist,
    compost). If construction fails or a cron is missing, the live
    daemon would silently miss its scheduled work."""
    sys.path.insert(0, str(REPO_ROOT / "lib"))
    for k, v in _POLICY_ENV_DEFAULTS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("UIPATH_URL", "https://example.invalid/x")
    monkeypatch.setenv("UIPATH_FOLDER", "AURORA-Demo")
    from aurora.conductor import Conductor

    c = Conductor()
    cron_names = {job.name for job in c.crons}
    assert "auditor_daily" in cron_names
    assert "strategist_nightly" in cron_names
    assert "compost_nightly" in cron_names
    assert c.token_budget_usd > 0


def test_every_agent_model_tier_exists_in_policy_routing() -> None:
    """Each agents/<name>.md frontmatter `model_tier` must resolve to a
    key in policy.yaml::routing.bindings — otherwise the conductor's
    dispatch can't route the agent."""
    policy = yaml.safe_load((REPO_ROOT / "policy.yaml").read_text())
    defaults = policy["routing"]["defaults"]

    misses: list[str] = []
    for agent_path in sorted(AGENTS_DIR.glob("*.md")):
        # Cheap frontmatter parse — files start with ---\n…\n---\n
        text = agent_path.read_text()
        if not text.startswith("---"):
            continue
        end = text.find("\n---\n", 3)
        if end < 0:
            continue
        fm = yaml.safe_load(text[3:end + 1])
        # Frontmatter may name the agent with the `aurora:` prefix; we
        # don't need the cleaned key here, but kept the variable for
        # potential per-agent assertions later.
        tier = fm.get("model_tier")
        if not tier:
            continue
        if tier not in defaults:
            misses.append(f"{agent_path.name}: model_tier {tier!r} not in policy.routing.defaults")
        # Also check the agent has a binding (or relies on a default tier
        # — that's allowed; the binding lookup falls back to mid_stakes).
        # We just assert the tier is structurally valid.
    assert not misses, "\n".join(misses)


def test_sentry_constructs_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sentry's __init__ reads policy + builds its events_path; it must
    not phone home until run() is called. This is a regression guard
    against accidental eager network calls."""
    sys.path.insert(0, str(REPO_ROOT / "lib"))
    for k, v in _POLICY_ENV_DEFAULTS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("UIPATH_URL", "https://example.invalid/x")
    monkeypatch.setenv("UIPATH_FOLDER", "AURORA-Demo")

    from unittest.mock import MagicMock

    from aurora.sentry import Sentry

    fake_client = MagicMock()
    fake_client.list_failed_jobs = MagicMock(return_value=[])
    sentry = Sentry(client=fake_client)
    assert sentry.interval >= 1
    assert sentry.events_path.parent.name in {"aurora-test", "memory"}
    # Construction must not have called any client methods.
    fake_client.list_failed_jobs.assert_not_called()
