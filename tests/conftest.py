"""Shared pytest fixtures for AURORA tests.

Conventions:
    - All tests are in tests/unit (no live UiPath / GitHub) or tests/integration
      (requires UIPATH_CLIENT_ID etc. — skipped when env is missing).
    - The `tmp_aurora_home` fixture isolates AURORA_HOME per test so memory and
      fingerprints don't bleed between cases.
    - The `fake_dotenv` fixture writes a temporary .env so auth tests don't
      touch the developer's real credentials.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure lib/ is importable when running pytest from the repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "lib"))


@pytest.fixture
def tmp_aurora_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Per-test AURORA_HOME — isolates memory, fingerprints, events."""
    home = tmp_path / "aurora-home"
    home.mkdir()
    monkeypatch.setenv("AURORA_HOME", str(home))
    return home


@pytest.fixture
def fake_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary .env that auth.write_to_dotenv can mutate without touching the real one."""
    p = tmp_path / ".env"
    p.write_text(
        "UIPATH_URL=https://cloud.example.test/acct/tenant/orchestrator_\n"
        "UIPATH_CLIENT_ID=fake-client\n"
        "UIPATH_CLIENT_SECRET=fake-secret\n"
        "UIPATH_FOLDER=Test-Folder\n"
        "UIPATH_ACTION_CATALOG=test_catalog\n"
        "GITHUB_ORG=test-org\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("UIPATH_URL", "https://cloud.example.test/acct/tenant/orchestrator_")
    monkeypatch.setenv("UIPATH_CLIENT_ID", "fake-client")
    monkeypatch.setenv("UIPATH_CLIENT_SECRET", "fake-secret")
    monkeypatch.setenv("UIPATH_FOLDER", "Test-Folder")
    monkeypatch.setenv("UIPATH_ACTION_CATALOG", "test_catalog")
    return p


@pytest.fixture
def sample_event() -> dict:
    """Canonical fault event used across fingerprint tests."""
    return {
        "ts": "2026-05-09T03:42:11Z",
        "kind": "job_failed",
        "scope": {"folder": "Test-Folder", "process": "TestProcess", "job_id": 1234567},
        "details": {
            "exception_type": "UiPath.Core.Activities.SelectorNotFoundException",
            "message": "Could not find selector <wnd app='chrome.exe' aaname='Inbox' /> after 30000ms",
            "step": "Workflows/GitHub/FetchLockfile.xaml",
        },
    }


@pytest.fixture
def integration_env_or_skip(request: pytest.FixtureRequest) -> dict[str, str]:
    """Skip tests in tests/integration/ when live credentials aren't available."""
    required = ("UIPATH_CLIENT_ID", "UIPATH_CLIENT_SECRET", "UIPATH_URL")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        pytest.skip(f"integration test needs {missing}; set in .env or skip")
    return {k: os.environ[k] for k in required}
