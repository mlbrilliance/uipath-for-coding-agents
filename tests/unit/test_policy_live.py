"""Unit tests for `aurora policy validate --live`.

The `--live` flag extends `--strict` with three real-world probes:
    1. Orchestrator: HEAD `/odata/Folders` against UIPATH_URL with the
       UIPATH_ACCESS_TOKEN bearer.
    2. GitHub: HEAD `/repos/{org}` against api.github.com with GITHUB_TOKEN.
    3. Action Center: GET `/api/CatalogIdentity?name={UIPATH_ACTION_CATALOG}`
       (returns 404 if the catalog is missing — that's a probe failure).

Each probe is independent. We aggregate failures and report them all in one
pass so the operator sees the full picture before they have to retry.

T-F2 acceptance criteria.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from aurora.policy_live import LiveProbeResult, run_live_probes


@pytest.fixture
def env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UIPATH_URL", "https://cloud.uipath.com/test/DefaultTenant/orchestrator_")
    monkeypatch.setenv("UIPATH_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("UIPATH_FOLDER", "AURORA-Demo")
    monkeypatch.setenv("UIPATH_ACTION_CATALOG", "aurora_supply_chain_approvals")
    monkeypatch.setenv("GITHUB_ORG", "aurora-demo-org")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-gh-token")


ORCH_URL = "https://cloud.uipath.com/test/DefaultTenant/orchestrator_/odata/Folders"
GH_URL = "https://api.github.com/users/aurora-demo-org"
CATALOG_URL = (
    "https://cloud.uipath.com/test/DefaultTenant/orchestrator_/odata/TaskCatalogs"
    "?%24filter=Name+eq+%27aurora_supply_chain_approvals%27"
)
# The catalog probe also GETs /odata/Folders (no params) to resolve
# folder name → numeric id before sending the X-UIPATH-OrganizationUnitId
# header. Mocked separately from ORCH_URL (which is HEAD-only).
FOLDERS_GET_URL = "https://cloud.uipath.com/test/DefaultTenant/orchestrator_/odata/Folders"
_FOLDER_LIST_BODY = {
    "value": [
        {"Id": 7838073, "DisplayName": "AURORA-Demo", "FullyQualifiedName": "AURORA-Demo"}
    ]
}


def test_all_probes_succeed(env_set: None, httpx_mock) -> None:
    """All three live endpoints return 2xx → no live errors reported."""
    httpx_mock.add_response(url=ORCH_URL, method="HEAD", status_code=200)
    httpx_mock.add_response(url=GH_URL, method="HEAD", status_code=200)
    # Catalog probe makes two GETs: first /odata/Folders to resolve
    # folder name → id, then /odata/TaskCatalogs?$filter=Name eq ...
    httpx_mock.add_response(url=FOLDERS_GET_URL, method="GET", json=_FOLDER_LIST_BODY)
    httpx_mock.add_response(
        url=CATALOG_URL,
        json={
            "@odata.count": 1,
            "value": [{"Name": "aurora_supply_chain_approvals", "Id": 21185}],
        },
    )

    result = run_live_probes()
    assert isinstance(result, LiveProbeResult)
    assert result.orchestrator_ok
    assert result.github_ok
    assert result.action_catalog_ok
    assert result.failures == []


def test_orchestrator_probe_fails_on_401(env_set: None, httpx_mock) -> None:
    """401 from Orchestrator means the token's stale or scope is missing.
    --live must surface this without raising."""
    httpx_mock.add_response(url=ORCH_URL, method="HEAD", status_code=401)
    httpx_mock.add_response(url=GH_URL, method="HEAD", status_code=200)
    httpx_mock.add_response(url=FOLDERS_GET_URL, method="GET", json=_FOLDER_LIST_BODY)
    httpx_mock.add_response(
        url=CATALOG_URL,
        json={"@odata.count": 1, "value": [{"Name": "aurora_supply_chain_approvals"}]},
    )

    result = run_live_probes()
    assert not result.orchestrator_ok
    assert any("orchestrator" in f.lower() and "401" in f for f in result.failures)


def test_github_probe_fails_on_404(env_set: None, httpx_mock) -> None:
    """404 from GitHub means the org doesn't exist or the token can't see it."""
    httpx_mock.add_response(url=ORCH_URL, method="HEAD", status_code=200)
    httpx_mock.add_response(url=GH_URL, method="HEAD", status_code=404)
    httpx_mock.add_response(url=FOLDERS_GET_URL, method="GET", json=_FOLDER_LIST_BODY)
    httpx_mock.add_response(
        url=CATALOG_URL,
        json={"@odata.count": 1, "value": [{"Name": "aurora_supply_chain_approvals"}]},
    )

    result = run_live_probes()
    assert not result.github_ok
    assert any("github" in f.lower() and "404" in f for f in result.failures)


def test_action_catalog_probe_fails_when_catalog_missing(
    env_set: None, httpx_mock,
) -> None:
    """Empty TaskCatalogs result = catalog hasn't been provisioned;
    runtime error 2451 will fire when Concierge first tries to create
    a Form Task. Surface here for the pre-flight."""
    httpx_mock.add_response(url=ORCH_URL, method="HEAD", status_code=200)
    httpx_mock.add_response(url=GH_URL, method="HEAD", status_code=200)
    httpx_mock.add_response(url=FOLDERS_GET_URL, method="GET", json=_FOLDER_LIST_BODY)
    httpx_mock.add_response(
        url=CATALOG_URL, json={"@odata.count": 0, "value": []},
    )

    result = run_live_probes()
    assert not result.action_catalog_ok
    assert any("catalog" in f.lower() for f in result.failures)


def test_missing_env_var_short_circuits_with_clear_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If UIPATH_URL isn't set, fail fast with a clear message — don't
    blame the network."""
    monkeypatch.delenv("UIPATH_URL", raising=False)
    monkeypatch.setenv("UIPATH_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("UIPATH_FOLDER", "AURORA-Demo")
    monkeypatch.setenv("UIPATH_ACTION_CATALOG", "x")
    monkeypatch.setenv("GITHUB_ORG", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "x")

    result = run_live_probes()
    assert not result.orchestrator_ok
    assert any(
        "UIPATH_URL" in f and ("missing" in f.lower() or "not set" in f.lower())
        for f in result.failures
    )


def test_network_error_is_caught_per_probe(env_set: None) -> None:
    """A connection-refused on Orchestrator must not crash the whole
    --live run; the GitHub and catalog probes should still try."""
    with patch("aurora.policy_live.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        # First call (orchestrator HEAD) raises; second (github HEAD) succeeds.
        mock_client.head.side_effect = [
            httpx.ConnectError("Connection refused"),  # orchestrator
            MagicMock(status_code=200),                # github
        ]
        # Third + fourth calls (folder lookup, then catalog GET) both via
        # client.get(...). Use side_effect with response objects.
        folder_resp = MagicMock(status_code=200)
        folder_resp.json.return_value = {
            "value": [{"Id": 7838073, "DisplayName": "AURORA-Demo"}]
        }
        # raise_for_status is called on the folder response; default MagicMock
        # makes it a no-op which is what we want for a 200.
        catalog_resp = MagicMock(status_code=200)
        catalog_resp.json.return_value = {
            "@odata.count": 1,
            "value": [{"Name": "aurora_supply_chain_approvals"}],
        }
        mock_client.get.side_effect = [folder_resp, catalog_resp]

        result = run_live_probes()
    assert not result.orchestrator_ok
    assert result.github_ok
    assert result.action_catalog_ok
    assert any("orchestrator" in f.lower() for f in result.failures)
