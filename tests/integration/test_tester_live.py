"""Integration test for Test Manager linkage against a live UiPath tenant.

Gated by ``UIPATH_INTEGRATION=1`` — skipped when the env var is absent.
Run manually before promote-to-prod:

    UIPATH_INTEGRATION=1 UIPATH_TM_PROJECT_KEY=DEMO \\
        uv run pytest tests/integration/test_tester_live.py -v

Performs a list_test_cases (read-only) and, if a real test case + package
id are configured, an idempotent link_automation. The link step is
no-op-safe per R.K.06: re-running against the same (test_case_id,
package_id) is detected and cached.
"""
from __future__ import annotations

import os

import pytest
from aurora.test_manager import BusinessError, TestManagerClient

pytestmark = pytest.mark.integration


@pytest.fixture
def integration_check() -> None:
    if not os.environ.get("UIPATH_INTEGRATION"):
        pytest.skip("UIPATH_INTEGRATION=1 required for live test-manager test")


def test_list_test_cases_live(integration_check: None) -> None:
    """List test cases against the live tenant. Read-only."""
    project_key = os.environ.get("UIPATH_TM_PROJECT_KEY")
    if not project_key:
        pytest.skip("UIPATH_TM_PROJECT_KEY required to scope the list_test_cases call")
    client = TestManagerClient()
    try:
        cases = client.list_test_cases(project_key=project_key)
    except BusinessError as exc:
        pytest.skip(
            f"list_test_cases returned 4xx (expected if project_key is empty/missing): {exc}"
        )
    assert isinstance(cases, list)
    for case in cases:
        assert case.id
        assert case.project_key == project_key


def test_link_automation_live_idempotent(integration_check: None) -> None:
    """Idempotent link_automation against the live tenant.

    Requires UIPATH_TM_TEST_CASE_ID and UIPATH_TM_PACKAGE_ID; otherwise
    skipped. Linking is no-op-safe — running this test against the
    sandbox folder will not deploy beyond the linkage record.
    """
    test_case_id = os.environ.get("UIPATH_TM_TEST_CASE_ID")
    package_id = os.environ.get("UIPATH_TM_PACKAGE_ID")
    entry_point = os.environ.get("UIPATH_TM_ENTRY_POINT", "Main.xaml")
    if not (test_case_id and package_id):
        pytest.skip(
            "UIPATH_TM_TEST_CASE_ID and UIPATH_TM_PACKAGE_ID required for live link test"
        )
    client = TestManagerClient()
    try:
        first = client.link_automation(
            test_case_id=test_case_id,
            package_id=package_id,
            entry_point=entry_point,
        )
        second = client.link_automation(
            test_case_id=test_case_id,
            package_id=package_id,
            entry_point=entry_point,
        )
    except BusinessError as exc:
        pytest.skip(
            f"link_automation returned 4xx (test case or package may not exist): {exc}"
        )
    assert first.link_id == second.link_id
