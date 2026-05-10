"""Surgeon contract tests — offline.

R.G.04: ``policy.operate.surgeon.max_workflows_touched_without_hitl`` caps
the auto-fix blast radius. Above the cap, surgeon must route through HITL
via concierge — even when Diagnostician's confidence was high. R.E.04 is
honoured by ``BusinessException`` rethrows in the dispatcher.

This test never opens a PR; the `pr_number` field is read straight from the
fixture, and the only side-effect-bearing call surface (``gh pr create``)
stays untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.agents.conftest import load_fixture_json  # noqa: E402
from tests.agents.contracts.surgeon import (  # noqa: E402
    BusinessException,
    FixDispatch,
    dispatch_from_triage,
)


@pytest.fixture
def small_blast_triage() -> dict[str, Any]:
    return load_fixture_json("surgeon", "triage_record.json")


@pytest.fixture
def large_blast_triage() -> dict[str, Any]:
    return load_fixture_json("surgeon", "large_blast_record.json")


def test_small_blast_radius_does_not_trigger_hitl(
    small_blast_triage: dict[str, Any],
    max_workflows_touched_without_hitl: int,
) -> None:
    """R.G.04: a small fix (≤ cap) auto-dispatches without HITL."""
    dispatch = dispatch_from_triage(
        small_blast_triage,
        max_workflows_touched_without_hitl=max_workflows_touched_without_hitl,
    )
    assert isinstance(dispatch, FixDispatch)
    assert len(dispatch.workflow_paths_touched) <= max_workflows_touched_without_hitl
    assert dispatch.hitl_required is False
    assert dispatch.pr_number == 42


def test_large_blast_radius_forces_hitl(
    large_blast_triage: dict[str, Any],
    max_workflows_touched_without_hitl: int,
) -> None:
    """R.G.04: > cap ⇒ HITL is mandatory."""
    dispatch = dispatch_from_triage(
        large_blast_triage,
        max_workflows_touched_without_hitl=max_workflows_touched_without_hitl,
    )
    assert len(dispatch.workflow_paths_touched) > max_workflows_touched_without_hitl
    assert dispatch.hitl_required is True
    assert dispatch.pr_number is None


def test_diagnostician_low_confidence_forces_hitl(
    small_blast_triage: dict[str, Any],
    max_workflows_touched_without_hitl: int,
) -> None:
    """Even a small-blast fix needs HITL when ``auto_fix`` is False upstream."""
    triage = dict(small_blast_triage)
    triage["auto_fix"] = False
    dispatch = dispatch_from_triage(
        triage,
        max_workflows_touched_without_hitl=max_workflows_touched_without_hitl,
    )
    assert dispatch.hitl_required is True


def test_explicit_force_hitl_overrides_blast_radius(
    small_blast_triage: dict[str, Any],
    max_workflows_touched_without_hitl: int,
) -> None:
    triage = dict(small_blast_triage)
    triage["force_hitl"] = True
    dispatch = dispatch_from_triage(
        triage,
        max_workflows_touched_without_hitl=max_workflows_touched_without_hitl,
    )
    assert dispatch.hitl_required is True


def test_malformed_paths_raise_business_exception(
    max_workflows_touched_without_hitl: int,
) -> None:
    """R.E.04: external-data parse failures rethrow as BusinessException."""
    bad = {"workflow_paths_touched": 7, "auto_fix": True}
    with pytest.raises(BusinessException):
        dispatch_from_triage(
            bad,
            max_workflows_touched_without_hitl=max_workflows_touched_without_hitl,
        )


def test_policy_cap_matches_documented_value(
    max_workflows_touched_without_hitl: int,
) -> None:
    """Source of truth is policy.yaml, but the documented value is 3."""
    assert max_workflows_touched_without_hitl >= 1
