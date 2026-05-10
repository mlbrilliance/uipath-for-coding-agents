"""Shared pytest fixtures for the GitHub check_run webhook tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

# Make the webhook source importable as `app`, `security`, `maestro_client`
# and the tests dir importable for `helpers`
_tests_dir = str(Path(__file__).resolve().parent)
_src_dir = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _src_dir)
sys.path.insert(0, _tests_dir)

from helpers import MaestroMock, make_check_run_payload, sign  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def secret() -> str:
    return "test-webhook-secret-12345"


@pytest.fixture
def check_run_payload() -> dict[str, Any]:
    return make_check_run_payload()


@pytest.fixture
def signed_payload(secret: str, check_run_payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(check_run_payload).encode()
    return {
        "body": body,
        "headers": {
            "X-Hub-Signature-256": sign(secret, body),
            "X-GitHub-Event": "check_run",
            "Content-Type": "application/json",
        },
    }


@pytest.fixture
def unsigned_payload(check_run_payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(check_run_payload).encode()
    return {
        "body": body,
        "headers": {
            "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
            "X-GitHub-Event": "check_run",
            "Content-Type": "application/json",
        },
    }


@pytest.fixture
def mock_maestro() -> MaestroMock:
    return MaestroMock()


@pytest.fixture
def client(
    secret: str,
    mock_maestro: MaestroMock,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("UIPATH_URL", "https://cloud.uipath.test/acct/tenant/orchestrator_")
    monkeypatch.setenv("UIPATH_FOLDER", "test-folder-id")
    monkeypatch.setenv("UIPATH_ACCESS_TOKEN", "fake-token")

    from app import app, get_maestro_client

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_maestro.handler))
    app.dependency_overrides[get_maestro_client] = lambda: mock_client

    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides.clear()
