"""Auditor contract tests — offline.

R.G.01 — no prod deploy without an Auditor drift-free verdict; R.G.02 —
cross-folder dependency check (a clean drift dataset). The validator emits
a typed ``DriftReport`` whose three lists must be populated for each
detected issue and empty for a clean tenant.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.agents.conftest import load_fixture_json  # noqa: E402
from tests.agents.contracts.auditor import (  # noqa: E402
    DriftReport,
    HashMismatch,
    IdleProcess,
    audit_from_dataset,
)


@pytest.fixture
def drift_dataset() -> dict[str, Any]:
    return load_fixture_json("auditor", "drift_dataset.json")


@pytest.fixture
def clean_dataset(drift_dataset: dict[str, Any]) -> dict[str, Any]:
    """A clean variant: no idle processes, no hash mismatches, low licence."""
    return {
        "as_of": drift_dataset["as_of"],
        "folder": drift_dataset["folder"],
        "processes": [
            {
                "name": p["name"],
                "last_run": p["last_run"],
                "days_since_last_run": 1,
                "owner_email": p["owner_email"],
            }
            for p in drift_dataset["processes"]
        ],
        "packages": [
            {
                "package": pkg["package"],
                "deployed_sha": "0" * 32,
                "repo_sha": "0" * 32,
            }
            for pkg in drift_dataset["packages"]
        ],
        "license": {"used": 4, "total": 50},
    }


def test_drift_dataset_surfaces_idle_process_hash_and_license(
    drift_dataset: dict[str, Any],
) -> None:
    """R.G.01/R.G.02: drift verdict must enumerate every detected issue."""
    report = audit_from_dataset(drift_dataset)
    assert isinstance(report, DriftReport)
    idle_names = {p.name for p in report.idle_processes}
    assert "LegacyExpenseReport" in idle_names
    assert all(isinstance(p, IdleProcess) for p in report.idle_processes)

    mismatched_pkgs = {m.package for m in report.hash_mismatches}
    assert "AuroraSupplyChainDefender" in mismatched_pkgs
    assert all(isinstance(m, HashMismatch) for m in report.hash_mismatches)

    assert report.license_util.used == 47
    assert report.license_util.total == 50
    assert report.license_util.pct == pytest.approx(0.94, abs=0.005)


def test_clean_dataset_yields_empty_report(clean_dataset: dict[str, Any]) -> None:
    """R.G.01: a clean tenant ⇒ both drift lists empty, license OK."""
    report = audit_from_dataset(clean_dataset)
    assert report.idle_processes == []
    assert report.hash_mismatches == []
    assert report.license_util.pct < 0.5


def test_idle_threshold_is_configurable(drift_dataset: dict[str, Any]) -> None:
    """Lowering the threshold surfaces additional candidates."""
    report = audit_from_dataset(drift_dataset, idle_days_threshold=5)
    idle_names = {p.name for p in report.idle_processes}
    assert "TimesheetReminder" in idle_names
    assert "LegacyExpenseReport" in idle_names


def test_license_pct_validation_rejects_oversubscription() -> None:
    with pytest.raises(ValueError):
        audit_from_dataset(
            {
                "processes": [],
                "packages": [],
                "license": {"used": 60, "total": 50},
            }
        )
