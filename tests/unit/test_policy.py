"""Unit tests for aurora.policy."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from aurora import policy as policy_mod

# A minimal valid policy used as a baseline; tests mutate copies.
VALID_POLICY: dict = {
    "version": 1,
    "identity": {
        "uipath_folder": "Test-Folder",
        "action_catalog": "test_catalog",
        "github_org": "test-org",
    },
    "uipath_scopes": ["OR.Folders", "OR.Tasks"],
    "discovery": {
        "sources": [{"kind": "slack_jsonl_fixture", "path": "./fixtures/test.jsonl"}],
        "min_score_for_build": 70,
        "scoring": {"weights": {"frequency": 0.4, "pain": 0.4, "feasibility": 0.2}},
    },
    "build": {
        "prefer_pattern_when": [{"if": "actor_count >= 2", "pick": "maestro"}],
        "test_coverage_floor": 0.8,
        "worktree_root": "/tmp/aurora-worktrees",
    },
    "deploy": {
        "dev":  {"auto": True},
        "test": {"auto": True},
        "prod": {"auto": False, "gate": "hitl_action_center"},
    },
    "operate": {
        "sentry": {"poll_interval_seconds": 30, "use_webhooks_when_available": True},
        "surgeon": {"max_auto_fixes_per_day": 5, "max_workflows_touched_without_hitl": 3},
    },
    "gates": [
        {
            "name": "prod_publish",
            "trigger": "publish to folder matching ^Production",
            "via": "action_center",
            "catalog": "test_catalog",
            "timeout_hours": 8,
        },
        {
            "name": "emergency_patch",
            "trigger": "severity == critical",
            "via": "action_center",
            "catalog": "test_catalog",
            "approvers_env": "AURORA_EMERGENCY_APPROVERS",
            "timeout_hours": 4,
            "on_timeout": "escalate",
        },
    ],
    "memory": {"root": "/tmp/aurora", "fingerprint_index": "sqlite"},
    "routing": {
        "defaults": {"high_stakes": "claude-opus-4-6", "mid_stakes": "claude-sonnet-4-6", "continuous": "claude-haiku-4-5-20251001"},
        "bindings": {"architect": "high_stakes", "forger-rpa": "mid_stakes", "sentry": "continuous"},
    },
    "budget": {"daily_usd": 50, "on_exceed": "pause_non_critical_fleets"},
}


@pytest.fixture
def schema_path(tmp_path: Path) -> Path:
    """Copy the real schema into tmp so tests don't depend on cwd."""
    real = Path(__file__).resolve().parents[2] / "policy.schema.json"
    target = tmp_path / "policy.schema.json"
    target.write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_expand_env_substitutes_known(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOO", "hello")
    result = policy_mod.expand_env({"a": "${FOO}-world", "b": ["${FOO}", "x"]})
    assert result == {"a": "hello-world", "b": ["hello", "x"]}


def test_expand_env_raises_on_unknown() -> None:
    with pytest.raises(policy_mod.PolicyError, match="UNRESOLVED_VAR_X"):
        policy_mod.expand_env("${UNRESOLVED_VAR_X}")


def test_validate_policy_passes_clean(schema_path: Path) -> None:
    warnings = policy_mod.validate_policy(VALID_POLICY, schema_path=schema_path)
    # The baseline has no soft warnings.
    assert isinstance(warnings, list)


def test_validate_policy_warns_low_coverage(schema_path: Path) -> None:
    p = json.loads(json.dumps(VALID_POLICY))
    p["build"]["test_coverage_floor"] = 0.5
    warnings = policy_mod.validate_policy(p, schema_path=schema_path)
    assert any("test_coverage_floor" in w for w in warnings)


def test_validate_policy_strict_raises_on_warning(schema_path: Path) -> None:
    p = json.loads(json.dumps(VALID_POLICY))
    p["build"]["test_coverage_floor"] = 0.5
    with pytest.raises(policy_mod.PolicyError, match="strict mode"):
        policy_mod.validate_policy(p, schema_path=schema_path, strict=True)


def test_validate_policy_rejects_schema_violation(schema_path: Path) -> None:
    p = json.loads(json.dumps(VALID_POLICY))
    p["version"] = 2  # schema pins to const 1
    with pytest.raises(policy_mod.PolicyError, match="version"):
        policy_mod.validate_policy(p, schema_path=schema_path)


def test_aurora_policy_resolves_model_for_agent() -> None:
    policy = policy_mod.AuroraPolicy(
        version=1,
        identity=VALID_POLICY["identity"],
        uipath_scopes=VALID_POLICY["uipath_scopes"],
        discovery=VALID_POLICY["discovery"],
        build=VALID_POLICY["build"],
        deploy=VALID_POLICY["deploy"],
        operate=VALID_POLICY["operate"],
        gates=VALID_POLICY["gates"],
        memory=VALID_POLICY["memory"],
        routing=VALID_POLICY["routing"],
        budget=VALID_POLICY["budget"],
        raw=VALID_POLICY,
    )
    assert policy.model_for_agent("architect") == "claude-opus-4-6"
    assert policy.model_for_agent("forger-rpa") == "claude-sonnet-4-6"
    # Unknown agent falls back to mid_stakes.
    assert policy.model_for_agent("unknown-agent") == "claude-sonnet-4-6"


def test_aurora_policy_gate_lookup() -> None:
    policy = policy_mod.AuroraPolicy(
        version=1,
        identity=VALID_POLICY["identity"],
        uipath_scopes=VALID_POLICY["uipath_scopes"],
        discovery=VALID_POLICY["discovery"],
        build=VALID_POLICY["build"],
        deploy=VALID_POLICY["deploy"],
        operate=VALID_POLICY["operate"],
        gates=VALID_POLICY["gates"],
        memory=VALID_POLICY["memory"],
        routing=VALID_POLICY["routing"],
        budget=VALID_POLICY["budget"],
        raw=VALID_POLICY,
    )
    g = policy.gate("emergency_patch")
    assert g["timeout_hours"] == 4
    with pytest.raises(KeyError):
        policy.gate("does_not_exist")
