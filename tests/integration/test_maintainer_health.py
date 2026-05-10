"""Integration test for the AuroraMaintainerHealth Coded Agent.

Calls the agent's `main(input)` against a real package (npm/lodash → the
canonical example of a healthy, well-maintained project). Exercises the
real OpenSSF Scorecard + GitHub commits APIs, so it's gated behind:

    AURORA_INTEGRATION=1
    GITHUB_TOKEN=…

When either is unset, the test skips.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _agent_dir() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "oss-supply-chain-defender"
        / "agents"
        / "maintainer-health"
    )


@pytest.fixture
def maintainer_health_main(monkeypatch: pytest.MonkeyPatch):
    """Import `main` from the agent package directly (it lives outside src/)."""
    agent_dir = _agent_dir()
    monkeypatch.syspath_prepend(str(agent_dir))
    # Drop any cached imports so a different agent's `main`/`models` doesn't shadow.
    for mod in ("main", "models", "tools", "tools.scorecard", "tools.commit_recency"):
        sys.modules.pop(mod, None)
    import main as agent_main  # type: ignore[import-not-found]
    return agent_main.main


def test_main_returns_non_stub_report_for_real_package(maintainer_health_main) -> None:
    if os.environ.get("AURORA_INTEGRATION") != "1":
        pytest.skip("set AURORA_INTEGRATION=1 to run live maintainer-health checks")
    if not os.environ.get("GITHUB_TOKEN"):
        pytest.skip("GITHUB_TOKEN required for live commit-recency lookup")

    payload = {
        "lockfiles": [
            {
                "repo": "node-app",
                "ecosystem": "npm",
                "deps": [
                    {
                        "ecosystem": "npm",
                        "name": "lodash/lodash",
                        "version": "4.17.21",
                        "depth": 1,
                    }
                ],
            }
        ]
    }

    report = maintainer_health_main(payload)

    # Shape assertions — verify we got a real MaintainerHealthReport, not a stub.
    assert "packages" in report and len(report["packages"]) == 1
    package = report["packages"][0]
    assert package["ecosystem"] == "npm"
    assert package["name"] == "lodash/lodash"
    assert package["version"] == "4.17.21"
    assert 0.0 <= package["health_score"] <= 10.0
    # Either the live API gave us a number, or both fields are explicitly None
    # (still valid — but at least one of the two upstream APIs should answer
    # for a project as visible as lodash, so we assert *some* signal landed).
    assert (
        package["scorecard_score"] is not None
        or package["commit_recency_days"] is not None
    ), "expected at least one upstream signal for lodash; got neither"
    assert isinstance(package["flags"], list)
    assert 0.0 <= report["aggregate_score"] <= 10.0
    assert isinstance(report["flagged_count"], int)
