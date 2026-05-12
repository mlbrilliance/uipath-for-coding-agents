"""Unit tests for Maestro publish bridge (HTTP-API wrapper + UI fallback).

TDD contract assertions that define the expected behaviour of
``UiPathClient.publish_maestro_project`` and
``aurora.playwright.publish_ui_fallback.publish_via_ui``.

All HTTP calls are mocked with ``pytest-httpx`` so these run offline.
Playwright is monkeypatched so no browser opens in CI.

Fixture shape: captured from a live Studio Web Publish click 2026-05-12.
The publish endpoint is
``/{account}/studio_/backend/api/Solution/{solution_id}/Publish-Requests``
with body keys ``packageName``/``locationKey``/``version``/``autoDeploy``/
``locationFQN``/``withClientPackaging``. This is a tenant-level publish
(not folder-scoped) — there is no ``X-UIPATH-OrganizationUnitId`` header.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from aurora.uipath_client import FolderRef, UiPathClient

FIXTURE_REQ = Path(__file__).resolve().parents[1] / "fixtures" / "maestro" / "publish_request.json"
FAKE_FOLDER_REF = FolderRef(name="AURORA-Demo", id=999)

ACCOUNT = "test-acct"
TENANT_ID = "11111111-2222-3333-4444-555555555555"
SOLUTION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

# When UIPATH_URL = https://cloud.example.test/test-acct/tenant/orchestrator_
# the publish code strips /orchestrator_ + the account suffix, then appends
# the fixture's url_path (which itself starts with "/{account}/...").
PUBLISH_URL = (
    f"https://cloud.example.test/{ACCOUNT}/studio_/backend/api/Solution/"
    f"{SOLUTION_ID}/Publish-Requests"
)


# ---------------------------------------------------------------------------
# Helper — build a client with env stubbed so __init__ doesn't blow up
# ---------------------------------------------------------------------------

def _client(monkeypatch: pytest.MonkeyPatch) -> UiPathClient:
    monkeypatch.setenv("UIPATH_URL", f"https://cloud.example.test/{ACCOUNT}/tenant/orchestrator_")
    monkeypatch.setenv("UIPATH_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("UIPATH_TENANT_ID", TENANT_ID)
    monkeypatch.setenv("UIPATH_ACCOUNT_SLUG", ACCOUNT)
    monkeypatch.setenv("UIPATH_SOLUTION_ID", SOLUTION_ID)
    client = UiPathClient(folder="AURORA-Demo")
    client.resolve_folder = lambda: FAKE_FOLDER_REF  # type: ignore[assignment]
    return client


# ---------------------------------------------------------------------------
# 1. The wrapper reads the captured fixture and builds a matching request
# ---------------------------------------------------------------------------

def test_publishes_with_recorded_fixture(httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """The wrapper reads the captured fixture, builds a request matching its
    shape (URL, method, body-keys), POSTs, and returns the parsed response."""
    httpx_mock.add_response(
        method="POST",
        url=PUBLISH_URL,
        json={"version": "1.0.2", "status": "Published"},
    )
    client = _client(monkeypatch)
    result = client.publish_maestro_project(
        project_dir=Path("/tmp/dummy-maestro-proj"),
        version_bump="patch",
    )
    assert result["version"] == "1.0.2"

    requests = httpx_mock.get_requests()
    assert len(requests) == 1
    req = requests[0]
    assert "/studio_/backend/api/Solution/" in str(req.url)
    assert "/Publish-Requests" in str(req.url)
    assert SOLUTION_ID in str(req.url)
    assert req.method == "POST"


# ---------------------------------------------------------------------------
# 2. Required headers are set
# ---------------------------------------------------------------------------

def test_publish_request_has_required_headers(httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """Authorization Bearer + tenant header + content-type are all set.

    Studio Web's Solution publish is tenant-scoped, not folder-scoped, so
    there's no X-UIPATH-OrganizationUnitId here — the tenant id is carried
    in ``x-uipath-tenantid`` and the body's ``locationKey``."""
    httpx_mock.add_response(
        url=PUBLISH_URL,
        json={"version": "1.0.0"},
    )
    client = _client(monkeypatch)
    client.publish_maestro_project(
        project_dir=Path("/tmp/dummy"), version_bump="patch",
    )
    req = httpx_mock.get_requests()[-1]
    auth = req.headers.get("authorization") or req.headers.get("Authorization")
    assert auth == "Bearer fake-token"
    tenant = req.headers.get("x-uipath-tenantid") or req.headers.get("X-Uipath-Tenantid")
    assert tenant == TENANT_ID
    assert "json" in (req.headers.get("content-type") or req.headers.get("Content-Type") or "").lower()


# ---------------------------------------------------------------------------
# 3. 4xx → BusinessError (not retried)
# ---------------------------------------------------------------------------

def test_publish_handles_4xx_with_business_exception(httpx_mock: pytest.HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    """4xx → BusinessError with status code; not retried (per R.E.03)."""
    httpx_mock.add_response(
        url=PUBLISH_URL,
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
    monkeypatch.setattr("time.sleep", lambda _: None)  # skip backoff delays
    httpx_mock.add_response(
        url=PUBLISH_URL,
        status_code=502,
    )
    httpx_mock.add_response(
        url=PUBLISH_URL,
        status_code=502,
    )
    httpx_mock.add_response(
        url=PUBLISH_URL,
        json={"version": "1.0.0"},
    )
    client = _client(monkeypatch)
    result = client.publish_maestro_project(
        project_dir=Path("/tmp/dummy"), version_bump="patch",
    )
    assert result["version"] == "1.0.0"
    assert len(httpx_mock.get_requests()) == 3


# ---------------------------------------------------------------------------
# 5. Missing solution_id surfaces a clear error
# ---------------------------------------------------------------------------

def test_publish_without_solution_id_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """If no solution_id can be resolved (no arg, no project metadata, no env),
    surface a clear BusinessError rather than firing a malformed request."""
    monkeypatch.setenv("UIPATH_URL", "https://cloud.example.test/x/y/orchestrator_")
    monkeypatch.setenv("UIPATH_ACCESS_TOKEN", "fake-token")
    monkeypatch.delenv("UIPATH_SOLUTION_ID", raising=False)
    client = UiPathClient(folder="AURORA-Demo")
    client.resolve_folder = lambda: FAKE_FOLDER_REF  # type: ignore[assignment]
    with pytest.raises(Exception) as exc:
        client.publish_maestro_project(
            project_dir=Path("/tmp/no-such-proj"), version_bump="patch",
        )
    assert "solution_id" in str(exc.value)


# ---------------------------------------------------------------------------
# 6. UI fallback is invocable with the same signature
# ---------------------------------------------------------------------------

def test_ui_fallback_is_invocable(monkeypatch: pytest.MonkeyPatch) -> None:
    """publish_ui_fallback.py exposes a sync ``publish_via_ui(...)`` callable
    with the same signature as the HTTP wrapper. Mock playwright so no
    browser opens.

    Skipped when playwright isn't installed in the test env (it's an
    optional runtime dep — see pyproject.toml `[[tool.mypy.overrides]]`
    note for `playwright.*`)."""
    pytest.importorskip("playwright.sync_api")
    monkeypatch.setenv("UIPATH_ACCOUNT_SLUG", "test-acct")
    monkeypatch.setenv("UIPATH_TENANT_SLUG", "test-tenant")

    mock_page = MagicMock()
    mock_page.wait_for_load_state = MagicMock()
    mock_publish_btn = MagicMock()
    mock_page.wait_for_selector.return_value = mock_publish_btn
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

    # Patch at the source module level since the function imports inside
    monkeypatch.setattr("playwright.sync_api.sync_playwright", mock_sync_pw)

    # Simulate _on_response callback firing when page.on("response", ...) registers it
    def _trigger_response_on_on(event: str, handler: object) -> None:
        if event == "response":
            mock_resp = MagicMock()
            mock_resp.url = "https://cloud.uipath.com/studio_/api/publish"
            mock_resp.request.method = "POST"
            mock_resp.json.return_value = {"version": "1.0.3", "status": "Published"}
            handler(mock_resp)

    mock_page.on = MagicMock(side_effect=_trigger_response_on_on)

    from aurora.playwright.publish_ui_fallback import publish_via_ui

    result = publish_via_ui(
        project_dir=Path("/tmp/dummy"),
        version_bump="patch",
    )
    assert "version" in result
    assert isinstance(result["version"], str)
    assert result["version"] == "1.0.3"


# ---------------------------------------------------------------------------
# 7. _build_publish_request is a pure helper
# ---------------------------------------------------------------------------

def test_build_publish_request_pure_helper() -> None:
    """_build_publish_request reads the fixture and returns a dict with
    url_path, method, headers, body — no I/O. All placeholders are
    substituted."""
    from aurora.uipath_client import _build_publish_request

    req = _build_publish_request(
        fixture_path=FIXTURE_REQ,
        access_token="tok",
        solution_id=SOLUTION_ID,
        package_name="my-proj",
        tenant_id=TENANT_ID,
        account=ACCOUNT,
        version="1.0.1",
    )
    assert req["method"] == "POST"
    assert ACCOUNT in req["url_path"]
    assert SOLUTION_ID in req["url_path"]
    assert "/Publish-Requests" in req["url_path"]

    auth = req["headers"].get("authorization") or req["headers"].get("Authorization")
    assert auth == "Bearer tok"
    tenant = req["headers"].get("x-uipath-tenantid") or req["headers"].get("X-Uipath-Tenantid")
    assert tenant == TENANT_ID

    assert req["body"]["packageName"] == "my-proj"
    assert req["body"]["version"] == "1.0.1"
    assert req["body"]["locationKey"] == TENANT_ID
    assert req["body"]["autoDeploy"] is False
    # No unsubstituted placeholders remain
    body_str = json.dumps(req["body"])
    assert "{{" not in body_str
    assert "{{" not in req["url_path"]


# ---------------------------------------------------------------------------
# 8. _parse_publish_response is a pure helper
# ---------------------------------------------------------------------------

def test_parse_publish_response_pure_helper() -> None:
    """_parse_publish_response returns a dict with at least 'version'."""
    from aurora.uipath_client import _parse_publish_response

    result = _parse_publish_response({"version": "2.0.0", "status": "Published"})
    assert result["version"] == "2.0.0"
    assert result["status"] == "Published"


# ---------------------------------------------------------------------------
# 9. _read_studio_web_solution_id picks up project-local metadata
# ---------------------------------------------------------------------------

def test_solution_id_resolved_from_project_metadata(tmp_path: Path) -> None:
    """If project_dir/.studio-web/solution_id exists, _read_studio_web_solution_id
    returns its content — letting us avoid env vars for the demo project."""
    from aurora.uipath_client import _read_studio_web_solution_id

    proj = tmp_path / "demo"
    (proj / ".studio-web").mkdir(parents=True)
    (proj / ".studio-web" / "solution_id").write_text(SOLUTION_ID + "\n")
    assert _read_studio_web_solution_id(proj) == SOLUTION_ID


def test_solution_id_resolved_from_project_json(tmp_path: Path) -> None:
    """Fallback: project.json::studioWebSolutionId."""
    from aurora.uipath_client import _read_studio_web_solution_id

    proj = tmp_path / "demo"
    proj.mkdir()
    (proj / "project.json").write_text(json.dumps({"studioWebSolutionId": SOLUTION_ID}))
    assert _read_studio_web_solution_id(proj) == SOLUTION_ID


def test_solution_id_missing_returns_none(tmp_path: Path) -> None:
    from aurora.uipath_client import _read_studio_web_solution_id

    proj = tmp_path / "demo"
    proj.mkdir()
    assert _read_studio_web_solution_id(proj) is None
