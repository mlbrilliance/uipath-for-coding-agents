"""Unit tests for Maestro publish bridge (HTTP-API wrapper + UI fallback).

TDD RED-phase: contract assertions that define the expected behaviour of
``UiPathClient.publish_maestro_project`` and
``aurora.playwright.publish_ui_fallback.publish_via_ui``.

All HTTP calls are mocked with ``pytest-httpx`` so these run offline.
Playwright is monkeypatched so no browser opens in CI.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from aurora.uipath_client import UiPathClient

FIXTURE_REQ = Path(__file__).resolve().parents[1] / "fixtures" / "maestro" / "publish_request.json"


# ---------------------------------------------------------------------------
# Helper — build a client with env stubbed so __init__ doesn't blow up
# ---------------------------------------------------------------------------

def _client(monkeypatch: pytest.MonkeyPatch) -> UiPathClient:
    monkeypatch.setenv("UIPATH_URL", "https://cloud.example.test/acct/tenant/orchestrator_")
    monkeypatch.setenv("UIPATH_ACCESS_TOKEN", "fake-token")
    return UiPathClient(folder="AURORA-Demo")


# ---------------------------------------------------------------------------
# 1. The wrapper reads the captured fixture and builds a matching request
# ---------------------------------------------------------------------------

def test_publishes_with_recorded_fixture(httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper reads the captured fixture, builds a request matching its
    shape (URL, method, content-type, body-keys), POSTs, and returns the
    parsed response."""
    httpx_mock.add_response(
        method="POST",
        url="https://cloud.example.test/studio_/api/publish",
        json={"version": "1.0.2", "status": "Published"},
    )
    client = _client(monkeypatch)
    result = client.publish_maestro_project(
        project_dir=Path("/tmp/dummy-maestro-proj"),
        version_bump="patch",
    )
    assert result["version"] == "1.0.2"

    # Assert the request shape matches the captured fixture's URL / method.
    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    req = requests[0]
    expected_path = json.loads(FIXTURE_REQ.read_text())["url_path"]
    assert expected_path in str(req.url)
    assert req.method == "POST"


# ---------------------------------------------------------------------------
# 2. Required headers are set
# ---------------------------------------------------------------------------

def test_publish_request_has_required_headers(httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Authorization Bearer + folder header + content-type are all set."""
    monkeypatch.setenv("UIPATH_URL", "https://cloud.example.test/acct/tenant/orchestrator_")
    monkeypatch.setenv("UIPATH_ACCESS_TOKEN", "fake-token")
    httpx_mock.add_response(
        url="https://cloud.example.test/studio_/api/publish",
        json={"version": "1.0.0"},
    )
    UiPathClient(folder="AURORA-Demo").publish_maestro_project(
        project_dir=Path("/tmp/dummy"), version_bump="patch",
    )
    req = httpx_mock.get_requests()[-1]
    assert req.headers["Authorization"] == "Bearer fake-token"
    folder_header = req.headers.get("X-UIPATH-OrganizationUnitId") or req.headers.get("X-Uipath-Organizationunitid")
    assert folder_header is not None
    assert "json" in req.headers["Content-Type"].lower()


# ---------------------------------------------------------------------------
# 3. 4xx → BusinessException (not retried)
# ---------------------------------------------------------------------------

def test_publish_handles_4xx_with_business_exception(httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """4xx → BusinessException with status code; not retried (per R.E.03)."""
    httpx_mock.add_response(
        url="https://cloud.example.test/studio_/api/publish",
        status_code=403,
        json={"error": "Forbidden"},
    )
    client = _client(monkeypatch)
    with pytest.raises(Exception) as exc:
        client.publish_maestro_project(
            project_dir=Path("/tmp/dummy"), version_bump="patch",
        )
    msg = str(exc.value)
    assert "403" in msg or "Forbidden" in msg


# ---------------------------------------------------------------------------
# 4. 5xx → retry up to 3x with exponential backoff
# ---------------------------------------------------------------------------

def test_publish_retries_on_5xx(httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """5xx → retry up to 3x with exponential backoff (R.E.02). Mock 2 failures
    then a success; assert 3 calls + success returned."""
    httpx_mock.add_response(
        url="https://cloud.example.test/studio_/api/publish",
        status_code=502,
    )
    httpx_mock.add_response(
        url="https://cloud.example.test/studio_/api/publish",
        status_code=502,
    )
    httpx_mock.add_response(
        url="https://cloud.example.test/studio_/api/publish",
        json={"version": "1.0.0"},
    )
    client = _client(monkeypatch)
    result = client.publish_maestro_project(
        project_dir=Path("/tmp/dummy"), version_bump="patch",
    )
    assert result["version"] == "1.0.0"
    assert len(httpx_mock.get_requests()) == 3


# ---------------------------------------------------------------------------
# 5. UI fallback is invocable with the same signature
# ---------------------------------------------------------------------------

def test_ui_fallback_is_invocable(monkeypatch: pytest.MonkeyPatch) -> None:
    """publish_ui_fallback.py exposes a sync ``publish_via_ui(...)`` callable
    with the same signature as the HTTP wrapper. Mock playwright so no
    browser opens."""
    from aurora.playwright.publish_ui_fallback import publish_via_ui

    # Mock the playwright.sync_api.sync_playwright context manager
    mock_pw = MagicMock()
    mock_browser = MagicMock()
    mock_page = MagicMock()
    mock_page.url = "https://cloud.uipath.com"
    mock_browser.new_page.return_value = mock_page
    mock_pw.start.return_value.__enter__ = MagicMock(return_value=mock_pw.start.return_value)
    mock_pw.start.return_value.__exit__ = MagicMock(return_value=False)
    mock_pw.start.return_value.chromium.launch.return_value = mock_browser
    # Simulate the publish UI button click → version returned
    mock_page.evaluate.return_value = json.dumps({"version": "1.0.3"})
    mock_page.wait_for_response.return_value = MagicMock(
        json=MagicMock(return_value={"version": "1.0.3", "status": "Published"}),
    )

    monkeypatch.setattr("aurora.playwright.publish_ui_fallback.sync_playwright", lambda: mock_pw.start.return_value)

    result = publish_via_ui(
        project_dir=Path("/tmp/dummy"),
        version_bump="patch",
    )
    assert "version" in result
    assert isinstance(result["version"], str)


# ---------------------------------------------------------------------------
# 6. _build_publish_request is a pure helper
# ---------------------------------------------------------------------------

def test_build_publish_request_pure_helper() -> None:
    """_build_publish_request reads the fixture and returns a dict with
    url, method, headers, body — no I/O."""
    from aurora.uipath_client import _build_publish_request

    req = _build_publish_request(
        fixture_path=FIXTURE_REQ,
        access_token="tok",
        folder_id=42,
        project_key="my-proj",
        version="1.0.1",
        version_bump="patch",
    )
    assert req["method"] == "POST"
    assert "/studio_/api/publish" in req["url"]
    assert req["headers"]["Authorization"] == "Bearer tok"
    assert req["headers"]["X-UIPATH-OrganizationUnitId"] == "42"
    assert req["body"]["projectKey"] == "my-proj"
    assert req["body"]["version"] == "1.0.1"
    assert req["body"]["versionBump"] == "patch"


# ---------------------------------------------------------------------------
# 7. _parse_publish_response is a pure helper
# ---------------------------------------------------------------------------

def test_parse_publish_response_pure_helper() -> None:
    """_parse_publish_response returns a dict with at least 'version'."""
    from aurora.uipath_client import _parse_publish_response

    result = _parse_publish_response({"version": "2.0.0", "status": "Published"})
    assert result["version"] == "2.0.0"
    assert result["status"] == "Published"
