"""Live integration test for the compost PR opener.

Gated by `AURORA_INTEGRATION=1` — opens a real GitHub PR against a
`compost-test` branch in the configured demo org. Skipped by default.

The full live flow (clone, branch, push, gate, gh pr create) is intentionally
left as a TODO until the demo org credentials and a sandbox repo are wired up
in CI. This module exists so T-B3's acceptance criteria can be exercised
end-to-end without disturbing default test runs.
"""
from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("AURORA_INTEGRATION") != "1",
    reason="set AURORA_INTEGRATION=1 to run live compost PR test",
)


def test_propose_skill_pr_opens_real_pr() -> None:
    """TODO: drive aurora.compost.propose_skill_pr against a sandbox repo:

    1. Seed `${AURORA_HOME}/learnings/<today>.jsonl` with a 3-occurrence,
       2-project synthetic cluster.
    2. Configure `AURORA_COMPOST_BASE_BRANCH=compost-test` so the PR targets
       a throwaway branch, not main.
    3. Provide `AURORA_COMPOST_APPROVERS=<demo-approver-email>`.
    4. Call `propose_skill_pr(..., dry_run=False)`.
    5. Assert the returned PrResult has a github.com/<org>/<repo>/pull/<n>
       URL, `state == "gate-pending"`, and `gate_task_id` is non-empty.
    6. Tear down: close the PR, delete the branch.
    """
    pytest.skip("live PR scaffolding pending demo-org credentials")
