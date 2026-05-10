"""Shared fixtures for the Operate-fleet agent contract tests.

Reads policy.yaml at the worktree root so tests stay in sync if the policy
moves underneath them.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.agents.contracts.diagnostician import DEFAULT_MIN_CONFIDENCE_FOR_AUTO_DISPATCH

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def policy() -> dict[str, Any]:
    return yaml.safe_load((REPO_ROOT / "policy.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def max_workflows_touched_without_hitl(policy: dict[str, Any]) -> int:
    """Source of truth for R.G.04 — read from policy.yaml.operate.surgeon."""
    return int(policy["operate"]["surgeon"]["max_workflows_touched_without_hitl"])


@pytest.fixture(scope="session")
def min_confidence_for_auto_dispatch(policy: dict[str, Any]) -> float:
    """Diagnostician auto-dispatch floor.

    Pulled from policy.operate.diagnostician.min_confidence_for_auto_dispatch
    when present; otherwise the documented default of 0.7 (per agent prompt).
    """
    diag = policy.get("operate", {}).get("diagnostician") or {}
    raw = diag.get("min_confidence_for_auto_dispatch")
    if raw is None:
        return DEFAULT_MIN_CONFIDENCE_FOR_AUTO_DISPATCH
    return float(raw)


@pytest.fixture(scope="session")
def action_catalog(policy: dict[str, Any]) -> str:
    return str(policy["identity"]["action_catalog"])


def load_fixture_json(agent: str, name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / agent / name).read_text(encoding="utf-8"))


def load_fixture_jsonl(agent: str, name: str) -> list[dict[str, Any]]:
    text = (FIXTURES_DIR / agent / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


@pytest.fixture
def sentry_state() -> dict[str, Any]:
    return load_fixture_json("sentry", "orchestrator_state.json")


@pytest.fixture
def sentry_recorded_events() -> list[dict[str, Any]]:
    return load_fixture_jsonl("sentry", "events_sample.jsonl")
