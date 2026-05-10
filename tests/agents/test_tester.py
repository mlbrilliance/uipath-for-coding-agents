"""T-G3b — Tester contract test.

Loads a recorded `published_pkg.json` fixture and asserts the
TestPackage shape Tester emits after the Studio→Orchestrator→Test
Manager Select-Automation hop (T-E1 owns the live wiring; this test
locks the contract so the data carrier doesn't drift).

Satisfies US-9, US-31.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.agents.contracts.tester import TestPackage

FIXTURE = Path(__file__).parent / "fixtures" / "tester" / "published_pkg.json"


def test_published_pkg_validates() -> None:
    pkg = TestPackage.model_validate(json.loads(FIXTURE.read_text()))
    assert pkg.nupkg_path.endswith(".nupkg")
    assert pkg.orchestrator_pkg_id
    assert pkg.test_manager_link is not None
    assert pkg.tests_total == pkg.tests_green
    assert 0.0 <= pkg.coverage <= 1.0


def test_test_manager_link_optional() -> None:
    """Per agents/tester.md, the Test Manager link may be `None` until configured."""
    pkg = TestPackage(
        nupkg_path="dist/Bare.0.1.0.nupkg",
        orchestrator_pkg_id="pkg_BARE",
    )
    assert pkg.test_manager_link is None
    assert pkg.coverage == 0.0


def test_nupkg_extension_is_enforced() -> None:
    with pytest.raises(ValueError):
        TestPackage(nupkg_path="dist/NotAPackage.zip", orchestrator_pkg_id="pkg_X")


def test_coverage_must_be_in_range() -> None:
    with pytest.raises(ValueError):
        TestPackage(
            nupkg_path="dist/X.0.1.0.nupkg",
            orchestrator_pkg_id="pkg_X",
            coverage=1.5,
        )


def test_tests_green_cannot_exceed_total_negative_guard() -> None:
    """Sanity: negative counts are rejected by `Field(ge=0)`."""
    with pytest.raises(ValueError):
        TestPackage(
            nupkg_path="dist/X.0.1.0.nupkg",
            orchestrator_pkg_id="pkg_X",
            tests_total=-1,
        )
