"""Unit tests for the Test Manager linkage bridge.

TDD contract assertions that define the expected behaviour of
``aurora.test_manager.TestManagerClient`` and the Playwright UI fallback
in ``aurora.playwright.test_manager_ui``.

The Test Manager API supports a documented ``link_automation`` operation
(syncing an Orchestrator package to an existing test case). It does NOT
support write-publishing test sets; that flow goes through ``uipath
publish`` to Orchestrator. T-E1 builds the linkage rail.

All HTTP calls are mocked with ``pytest-httpx`` so these run offline.
Playwright is monkey-patched so no browser opens in CI.
"""
from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest

LIST_URL_RE = re.compile(r".*/test_/api/v1/testCases.*")
LINK_URL_RE = re.compile(r".*/test_/api/v1/.*[Ll]ink.*")
ANY_TM_URL_RE = re.compile(r".*/test_/api/v1/.*")


def _setup_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UIPATH_URL", "https://cloud.example.test/acct/tenant/orchestrator_")
    monkeypatch.setenv("UIPATH_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("UIPATH_FOLDER", "AURORA-Demo")


# ---------------------------------------------------------------------------
# 1. list_test_cases hits the documented OData-shaped endpoint
# ---------------------------------------------------------------------------

def test_list_test_cases_uses_correct_odata_endpoint(
    httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(monkeypatch)
    httpx_mock.add_response(
        url=LIST_URL_RE,
        json={
            "value": [
                {"Id": "TC-1", "Name": "RegressionA", "ProjectKey": "DEMO"},
                {"Id": "TC-2", "Name": "RegressionB", "ProjectKey": "DEMO"},
            ]
        },
    )
    from aurora.test_manager import TestManagerClient

    client = TestManagerClient()
    cases = client.list_test_cases(project_key="DEMO")
    assert len(cases) == 2
    assert cases[0].id == "TC-1"
    assert cases[0].name == "RegressionA"
    assert cases[0].project_key == "DEMO"

    req = httpx_mock.get_requests()[-1]
    assert "/test_/api/v1/testCases" in str(req.url)
    assert "DEMO" in str(req.url)


# ---------------------------------------------------------------------------
# 2. link_automation POSTs to the link endpoint and returns LinkResult
# ---------------------------------------------------------------------------

def test_link_automation_posts_to_link_endpoint(
    httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=LINK_URL_RE,
        json={"linkId": "L-100", "linked": True},
    )
    from aurora.test_manager import LinkResult, TestManagerClient

    client = TestManagerClient()
    result = client.link_automation(
        test_case_id="TC-1",
        package_id="MyPackage",
        entry_point="Main.xaml",
    )
    assert isinstance(result, LinkResult)
    assert result.link_id == "L-100"
    assert result.linked is True

    req = httpx_mock.get_requests()[-1]
    assert req.method == "POST"
    assert "/test_/api/v1/" in str(req.url)
    assert "link" in str(req.url).lower()


# ---------------------------------------------------------------------------
# 3. 4xx → BusinessError-like surfacing (no retry per R.E.03)
# ---------------------------------------------------------------------------

def test_link_handles_4xx_with_business_error(
    httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=ANY_TM_URL_RE,
        status_code=404,
        json={"error": "Test case not found"},
    )
    from aurora.test_manager import TestManagerClient

    client = TestManagerClient()
    with pytest.raises(Exception) as exc:
        client.link_automation(
            test_case_id="missing",
            package_id="X",
            entry_point="Main.xaml",
        )
    msg = str(exc.value)
    assert "404" in msg or "not found" in msg.lower()

    # only one request — 4xx is not retried (R.E.03)
    assert len(httpx_mock.get_requests()) == 1


# ---------------------------------------------------------------------------
# 4. 5xx → retry up to 3x with exponential backoff (R.E.02)
# ---------------------------------------------------------------------------

def test_link_retries_on_5xx(
    httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per R.E.02, retry up to 3x with backoff on transient failures."""
    _setup_env(monkeypatch)
    monkeypatch.setattr("time.sleep", lambda _: None)  # skip backoff delays

    httpx_mock.add_response(
        method="POST", url=ANY_TM_URL_RE, status_code=502, is_reusable=True
    )
    httpx_mock.add_response(
        method="POST", url=ANY_TM_URL_RE, status_code=502, is_reusable=True
    )
    httpx_mock.add_response(
        method="POST", url=ANY_TM_URL_RE, json={"linkId": "L-1", "linked": True}
    )

    from aurora.test_manager import TestManagerClient

    client = TestManagerClient()
    result = client.link_automation(
        test_case_id="TC-1", package_id="X", entry_point="Main.xaml"
    )
    assert result.linked
    assert len(httpx_mock.get_requests()) == 3


# ---------------------------------------------------------------------------
# 5. Idempotent: linking the same (test_case_id, package_id) twice
#    returns the same LinkResult, never raises (R.K.06).
# ---------------------------------------------------------------------------

def test_link_automation_is_idempotent(
    httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_env(monkeypatch)
    httpx_mock.add_response(
        method="POST",
        url=ANY_TM_URL_RE,
        json={"linkId": "L-42", "linked": True},
        is_reusable=True,
    )
    from aurora.test_manager import TestManagerClient

    client = TestManagerClient()
    first = client.link_automation(
        test_case_id="TC-1", package_id="MyPackage", entry_point="Main.xaml"
    )
    second = client.link_automation(
        test_case_id="TC-1", package_id="MyPackage", entry_point="Main.xaml"
    )
    assert first.link_id == second.link_id
    assert first.linked is True
    assert second.linked is True


# ---------------------------------------------------------------------------
# 6. Playwright UI fallback is invocable with the same shape as the API
# ---------------------------------------------------------------------------

def test_link_via_ui_is_invocable(monkeypatch: pytest.MonkeyPatch) -> None:
    """``link_via_ui(...)`` returns LinkResult, mocking playwright.

    Skipped when playwright isn't installed in the test env (matches the
    T-D3 publish-fallback pattern).
    """
    pytest.importorskip("playwright.sync_api")
    monkeypatch.setenv("UIPATH_ACCOUNT_SLUG", "test-acct")
    monkeypatch.setenv("UIPATH_TENANT_SLUG", "test-tenant")

    mock_page = MagicMock()
    mock_link_btn = MagicMock()
    mock_page.wait_for_selector.return_value = mock_link_btn
    mock_page.wait_for_load_state = MagicMock()
    mock_page.wait_for_timeout = MagicMock()
    mock_page.url = "https://cloud.uipath.com"

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_playwright = MagicMock()
    mock_playwright.chromium.launch.return_value = mock_browser

    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_playwright)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_sync_pw = MagicMock(return_value=mock_cm)

    def _trigger_response_on_on(event: str, handler: object) -> None:
        if event == "response":
            mock_resp = MagicMock()
            mock_resp.url = "https://cloud.uipath.com/test_/api/v1/automations/link"
            mock_resp.request.method = "POST"
            mock_resp.json.return_value = {"linkId": "L-200", "linked": True}
            handler(mock_resp)

    mock_page.on = MagicMock(side_effect=_trigger_response_on_on)
    monkeypatch.setattr("playwright.sync_api.sync_playwright", mock_sync_pw)

    from aurora.playwright.test_manager_ui import link_via_ui
    from aurora.test_manager import LinkResult

    result = link_via_ui(
        test_case_id="TC-1",
        package_id="MyPackage",
        entry_point="Main.xaml",
    )
    assert isinstance(result, LinkResult)
    assert result.link_id == "L-200"
    assert result.linked is True


# ---------------------------------------------------------------------------
# 7. _build_link_request is a pure helper (R.K.01)
# ---------------------------------------------------------------------------

def test_build_link_request_pure_helper() -> None:
    from aurora.test_manager import _build_link_request

    spec = _build_link_request(
        access_token="tok",
        folder_id=42,
        test_case_id="TC-1",
        package_id="MyPackage",
        entry_point="Main.xaml",
    )
    assert spec["method"] == "POST"
    assert "/test_/api/v1/" in spec["url_path"]
    assert "link" in spec["url_path"].lower()
    assert spec["headers"]["Authorization"] == "Bearer tok"
    assert spec["headers"]["X-UIPATH-OrganizationUnitId"] == "42"
    assert "json" in spec["headers"]["Content-Type"].lower()
    body = spec["body"]
    body_blob = str(body) + spec["url_path"]
    assert "TC-1" in body_blob
    assert body["packageId"] == "MyPackage"
    assert body["entryPoint"] == "Main.xaml"


# ---------------------------------------------------------------------------
# 8. _parse_link_response is a pure helper (R.K.01)
# ---------------------------------------------------------------------------

def test_parse_link_response_pure_helper() -> None:
    from aurora.test_manager import LinkResult, _parse_link_response

    result = _parse_link_response({"linkId": "L-9", "linked": True})
    assert isinstance(result, LinkResult)
    assert result.link_id == "L-9"
    assert result.linked is True


# ---------------------------------------------------------------------------
# 9. TestCase dataclass shape
# ---------------------------------------------------------------------------

def test_testcase_dataclass_shape() -> None:
    from aurora.test_manager import TestCase

    tc = TestCase(id="TC-1", name="X", project_key="DEMO")
    assert tc.id == "TC-1"
    assert tc.name == "X"
    assert tc.project_key == "DEMO"
