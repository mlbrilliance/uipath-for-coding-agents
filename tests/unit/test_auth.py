"""Unit tests for aurora.auth.

Network calls are mocked with httpx-mock so these run offline.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from aurora import auth
from pytest_httpx import HTTPXMock  # type: ignore[import-not-found]


def test_derive_identity_endpoint_cloud_uipath_uses_account_level_path() -> None:
    """Cloud (cloud.uipath.com) puts /identity_ at the host root, NOT at
    the tenant root. Verified against the OpenID-discovery doc at
    https://cloud.uipath.com/identity_/.well-known/openid-configuration
    which advertises token_endpoint = https://cloud.uipath.com/identity_/connect/token.
    Earlier implementation produced /webfiji/DefaultTenant/identity_/...
    which 404s in production."""
    url = "https://cloud.uipath.com/webfiji/DefaultTenant/orchestrator_"
    assert (
        auth.derive_identity_endpoint(url)
        == "https://cloud.uipath.com/identity_/connect/token"
    )


def test_derive_identity_endpoint_cloud_no_orchestrator_suffix() -> None:
    """Even without the /orchestrator_ suffix, cloud must collapse to host."""
    url = "https://cloud.uipath.com/webfiji/DefaultTenant"
    assert (
        auth.derive_identity_endpoint(url)
        == "https://cloud.uipath.com/identity_/connect/token"
    )


def test_derive_identity_endpoint_self_hosted_strips_orchestrator() -> None:
    """Self-hosted UiPath puts /identity_ as a sibling of /orchestrator_
    under the same host/tenant prefix."""
    url = "https://uipath.acme.local/orchestrator_"
    assert (
        auth.derive_identity_endpoint(url)
        == "https://uipath.acme.local/identity_/connect/token"
    )


def test_derive_identity_endpoint_self_hosted_with_tenant_path() -> None:
    url = "https://uipath.acme.local/AcmeTenant/orchestrator_"
    assert (
        auth.derive_identity_endpoint(url)
        == "https://uipath.acme.local/AcmeTenant/identity_/connect/token"
    )


def test_token_needs_refresh_when_close_to_expiry() -> None:
    fresh = auth.Token(access_token="x", expires_at=int(time.time()) + 3600, scope="OR.Folders")
    stale = auth.Token(access_token="x", expires_at=int(time.time()) + 60, scope="OR.Folders")
    assert not fresh.needs_refresh
    assert stale.needs_refresh


def test_mint_token_writes_sidecar_and_dotenv(
    fake_dotenv: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://cloud.example.test/acct/tenant/identity_/connect/token",
        json={
            "access_token": "fresh-token-abc",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "OR.Folders OR.Tasks",
        },
    )

    # Redirect the sidecar path
    sidecar = tmp_path / "sidecar.json"
    monkeypatch.setattr(auth, "SIDECAR_PATH", sidecar)

    token = auth.mint_token(write_dotenv_path=fake_dotenv)

    assert token.access_token == "fresh-token-abc"
    assert sidecar.exists()
    sidecar_data = json.loads(sidecar.read_text())
    assert sidecar_data["access_token"] == "fresh-token-abc"

    # .env was updated
    env_text = fake_dotenv.read_text()
    assert "UIPATH_ACCESS_TOKEN=fresh-token-abc" in env_text


def test_mint_token_redacts_secret_on_error(
    fake_dotenv: Path,
    monkeypatch: pytest.MonkeyPatch,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://cloud.example.test/acct/tenant/identity_/connect/token",
        status_code=401,
        text='{"error":"invalid_client","secret_echo":"fake-secret"}',
    )

    with pytest.raises(auth.AuthError) as exc_info:
        auth.mint_token(write_dotenv_path=fake_dotenv)

    msg = str(exc_info.value)
    assert "fake-secret" not in msg
    assert "***REDACTED***" in msg


def test_write_to_dotenv_replaces_existing_line(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("UIPATH_ACCESS_TOKEN=old\nFOO=bar\n", encoding="utf-8")
    auth.write_to_dotenv(p, "UIPATH_ACCESS_TOKEN", "new")
    text = p.read_text()
    assert "UIPATH_ACCESS_TOKEN=new" in text
    assert "UIPATH_ACCESS_TOKEN=old" not in text
    assert "FOO=bar" in text


def test_write_to_dotenv_appends_when_missing(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    p.write_text("FOO=bar\n", encoding="utf-8")
    auth.write_to_dotenv(p, "UIPATH_ACCESS_TOKEN", "new")
    text = p.read_text()
    assert "UIPATH_ACCESS_TOKEN=new" in text
    assert "FOO=bar" in text
