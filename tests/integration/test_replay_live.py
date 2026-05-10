"""Live integration test for sandbox-folder twin replay.

Skipped unless UIPATH_INTEGRATION is explicitly set, AND the usual
UiPath credentials are present. Don't run on shared CI.

Scenario (TODO — implement when a known-faulted instance fixture exists in
the demo tenant):

    1. Resolve a recent faulted Maestro instance in $UIPATH_FOLDER.
    2. Call aurora.replay.replay_instance(instance_id) with default sandbox
       folder ($UIPATH_FOLDER-Sandbox).
    3. Assert ReplayResult fields match expected shape:
        - sandbox_instance_id is non-empty
        - same_path / same_end_event / same_vars_at_each_gateway populated
        - divergence_step is set whenever same_path is False
    4. Tear down: pause the sandbox instance so it doesn't keep running.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


def test_replay_against_live_tenant_smoke() -> None:
    if not os.environ.get("UIPATH_INTEGRATION"):
        pytest.skip("set UIPATH_INTEGRATION=1 (with live tenant creds) to run")
    pytest.skip("TODO: implement against a known-faulted instance fixture in the demo tenant")
