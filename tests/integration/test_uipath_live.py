"""Integration tests against a live UiPath Automation Cloud tenant.

Skipped automatically when UIPATH_CLIENT_ID / UIPATH_CLIENT_SECRET / UIPATH_URL
aren't in the env. Run locally with:

    UIPATH_CLIENT_ID=… UIPATH_CLIENT_SECRET=… UIPATH_URL=… \
      uv run pytest tests/integration -v

These touch a real tenant. Don't run in CI on PRs from external contributors.
"""
from __future__ import annotations

import os

import pytest

from aurora import auth
from aurora.uipath_client import UiPathClient


pytestmark = pytest.mark.integration


def test_mint_token_against_live_tenant(integration_env_or_skip: dict[str, str]) -> None:
    """Mints a real token; verifies expiry shape; doesn't write the sidecar."""
    token = auth.mint_token(
        scopes="OR.Folders OR.Tasks",
        write_sidecar=False,
    )
    assert token.access_token
    assert token.expires_at > 0
    assert "OR.Folders" in token.scope


def test_resolve_demo_folder(integration_env_or_skip: dict[str, str]) -> None:
    folder = os.environ.get("UIPATH_FOLDER", "AURORA-Demo")
    client = UiPathClient(folder=folder)
    ref = client.resolve_folder()
    assert ref.name in (folder, f"Shared/{folder}")
    assert ref.id > 0


def test_list_failed_jobs_returns_a_list(integration_env_or_skip: dict[str, str]) -> None:
    client = UiPathClient()
    jobs = client.list_failed_jobs(since_minutes=1440)  # last 24h
    assert isinstance(jobs, list)
    # Field shape sanity
    if jobs:
        assert "Id" in jobs[0]
        assert "State" in jobs[0]
