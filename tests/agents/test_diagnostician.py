"""Diagnostician contract tests — offline.

The agent prompt (``agents/diagnostician.md``) defines two confidence
thresholds:

    * ``≥ 0.7`` — confident, dispatch surgeon with ``auto_fix == True``
      (matches the policy floor ``min_confidence_for_auto_dispatch``).
    * ``< 0.5`` — uncertain/novel, never auto-dispatch.

Cluster seeds with peers + prior resolutions clear the bar; novel-fault
single events do not. Per R.T.04, the error path (no peers) is mandatory.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.agents.conftest import load_fixture_json  # noqa: E402
from tests.agents.contracts.diagnostician import (  # noqa: E402
    TriageRecord,
    triage_from_cluster,
)


@pytest.fixture
def cluster_seed() -> dict[str, Any]:
    return load_fixture_json("diagnostician", "cluster_seed.json")


@pytest.fixture
def single_event() -> dict[str, Any]:
    return load_fixture_json("diagnostician", "single_event.json")


def test_cluster_seed_yields_auto_dispatch_record(
    cluster_seed: dict[str, Any], min_confidence_for_auto_dispatch: float
) -> None:
    """Cluster ≥ threshold ⇒ auto_fix == True."""
    record = triage_from_cluster(
        cluster_seed,
        min_confidence_for_auto_dispatch=min_confidence_for_auto_dispatch,
    )
    assert isinstance(record, TriageRecord)
    assert 0.0 <= record.confidence <= 1.0
    assert record.confidence >= min_confidence_for_auto_dispatch
    assert record.auto_fix is True
    assert record.cluster_size == cluster_seed["cluster_size"]


def test_single_event_below_threshold_blocks_auto_dispatch(
    single_event: dict[str, Any], min_confidence_for_auto_dispatch: float
) -> None:
    """A novel single-event cluster ⇒ confidence < 0.5 ⇒ auto_fix == False."""
    record = triage_from_cluster(
        single_event,
        min_confidence_for_auto_dispatch=min_confidence_for_auto_dispatch,
    )
    assert record.confidence < 0.5
    assert record.auto_fix is False


def test_confidence_is_clamped_into_unit_interval() -> None:
    out_of_range = {
        "cluster_id": "x",
        "root_cause": "y",
        "fix_hypothesis": "z",
        "cluster_size": 99,
        "prior_resolutions": 99,
        "base_confidence": 1.42,
    }
    record = triage_from_cluster(out_of_range)
    assert 0.0 <= record.confidence <= 1.0


def test_triage_record_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError):
        TriageRecord(
            cluster_id="c",
            root_cause="r",
            confidence=1.5,
            fix_hypothesis="f",
        )


def test_threshold_pulled_from_policy_fixture(
    min_confidence_for_auto_dispatch: float,
) -> None:
    """Sanity check: threshold lives in policy / contract default, not in code."""
    assert 0.0 < min_confidence_for_auto_dispatch <= 1.0
