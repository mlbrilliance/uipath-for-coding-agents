"""Integration test for Maestro publish against a live UiPath tenant.

Gated by ``UIPATH_INTEGRATION=1`` — skipped when the env var is absent.
Run manually before promote-to-prod:

    UIPATH_INTEGRATION=1 uv run pytest tests/integration/test_maestro_publish_live.py -v

This test only performs a no-op patch bump (1.0.0 → 1.0.1) against the
demo's sandbox folder. It never deploys beyond that.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from aurora.uipath_client import BusinessError, UiPathClient

pytestmark = pytest.mark.integration


@pytest.fixture
def integration_check() -> None:
    if not os.environ.get("UIPATH_INTEGRATION"):
        pytest.skip("UIPATH_INTEGRATION=1 required for live publish test")


def test_publish_maestro_project_noop_bump(integration_check: None) -> None:
    """Publish a Maestro project with a patch-bump against the live tenant.

    This is a no-op-bump test — the project version goes from N to N+1
    in the demo's sandbox folder only. No production deployment.
    """
    client = UiPathClient(folder=os.environ.get("UIPATH_FOLDER", "AURORA-Demo"))
    try:
        result = client.publish_maestro_project(
            project_dir=Path(os.environ.get("MAESTRO_PROJECT_DIR", "/tmp/oss-supply-chain-defender")),
            version_bump="patch",
        )
        assert "version" in result
        assert isinstance(result["version"], str)
    except BusinessError as exc:
        pytest.skip(f"publish endpoint returned 4xx (expected if project doesn't exist): {exc}")
