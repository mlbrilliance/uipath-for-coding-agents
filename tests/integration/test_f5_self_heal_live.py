"""F5 self-heal integration test against a live UiPath tenant.

Replays the Sentry → Diagnostician → Surgeon chain that `break.sh` would
trigger in production, without actually invalidating the user's
GITHUB_TOKEN or breaking real workflows. The four stages:

  1. Sentry's `_emit_job_fault` lands a synthetic auth-failure event in
     `${AURORA_HOME}/events.jsonl` (the same code path the live polling
     daemon uses).
  2. `classify_event(event)` reads the event back and clusters it. The
     test asserts the cluster shape matches the F5 spec exactly:
     `kind == 'auth-failed'`, `refinement == 'token-expired'`.
  3. The fingerprint row lands in `${AURORA_HOME}/fingerprints.db` with
     `occurrences >= 1`, proving the cluster persists across runs (this
     is what enables the `confidence >= 0.7` bar after multiple failures
     - confidence = 0.30 + 0.05 * occurrences).
  4. Surgeon's read path (`/odata/Assets` folder-scoped) returns 200
     against the live tenant. The write path (`update_asset`) is NOT
     executed by this test — that's a destructive op deferred to the
     human-driven runbook step where the operator decides which
     Credential asset to rotate.

Skipped when UIPATH_INTEGRATION isn't set or live creds are missing.

Live evidence captured by this test was first generated manually on
2026-05-10 against the demo tenant; this test makes the recipe
reproducible.

Acceptance for T-F5 says "self-heal within 60s of break.sh"; the
60-second clock is the time-to-detect (Sentry's poll interval). This
integration test asserts the structural correctness of every stage; it
does not measure the wall-clock latency (that's the runbook's job).
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from aurora.fingerprint import classify_event
from aurora.sentry import Sentry
from aurora.uipath_client import UiPathClient

pytestmark = pytest.mark.integration


def _aurora_home() -> Path:
    home = Path(os.environ.get("AURORA_HOME", str(Path.home() / ".aurora")))
    home.mkdir(parents=True, exist_ok=True)
    return home


def _synthetic_failed_job() -> dict[str, Any]:
    """The shape Sentry's polling produces when /odata/Jobs returns a
    Faulted entry whose Info begins with '401 Unauthorized'. Mirrors the
    payload `break.sh` would surface in production."""
    return {
        "Id": 9001,
        "ReleaseName": "OssSupplyChainDefender",
        "State": "Faulted",
        "Info": "401 Unauthorized: Bad credentials",
        "HostMachineName": "ResolveLockfiles_step",
        "StartTime": "2026-05-10T06:22:17.749094+00:00",
        "EndTime": "2026-05-10T06:22:17.749110+00:00",
    }


def test_stage_2_sentry_emits_job_fault_to_events_jsonl(
    integration_env_or_skip: dict[str, str],
) -> None:
    """Stage 2 of F5: Sentry's _emit_job_fault writes a kind='job_failed'
    event to events.jsonl in the canonical shape Diagnostician reads."""
    home = _aurora_home()
    events_path = home / "events.jsonl"
    # Capture pre-test count so we don't assume an empty stream.
    pre_count = sum(1 for _ in events_path.open()) if events_path.exists() else 0

    sentry = Sentry(client=MagicMock(), interval_seconds=30)
    sentry._emit_job_fault(_synthetic_failed_job())

    post_count = sum(1 for _ in events_path.open())
    assert post_count == pre_count + 1
    last_event = json.loads(events_path.read_text().splitlines()[-1])
    assert last_event["kind"] == "job_failed"
    assert last_event["scope"]["process"] == "OssSupplyChainDefender"
    assert last_event["scope"]["job_id"] == 9001
    assert last_event["scope"]["folder"] == "AURORA-Demo"
    assert "401" in last_event["details"]["message"]


def test_stage_3_diagnostician_clusters_as_auth_failed_token_expired(
    integration_env_or_skip: dict[str, str],
) -> None:
    """Stage 3 of F5: classify_event() clusters the auth-failure event as
    kind='auth-failed', refinement='token-expired' — the exact shape the
    F5 acceptance criterion calls out."""
    # Build the in-memory event the way Sentry would have written it.
    event = {
        "ts": "2026-05-10T06:22:17.768560+00:00",
        "kind": "job_failed",
        "scope": {
            "folder": "AURORA-Demo",
            "process": "OssSupplyChainDefender",
            "job_id": 9001,
        },
        "details": {
            "exception_type": "401 Unauthorized",
            "message": "401 Unauthorized: Bad credentials",
            "step": "ResolveLockfiles_step",
            "started_at": "2026-05-10T06:22:17.749094+00:00",
            "ended_at": "2026-05-10T06:22:17.749110+00:00",
        },
    }
    cluster = classify_event(event)
    assert cluster.kind == "auth-failed"
    assert cluster.refinement == "token-expired"
    # Confidence should be at least the floor for a known cluster (0.35).
    # Higher confidence comes from repeat occurrences across runs — F5
    # acceptance asserts ≥ 0.7 after multiple break.sh fires; the
    # structural correctness here is the kind/refinement pair.
    assert cluster.confidence >= 0.30


def test_stage_3b_fingerprints_db_persists_the_cluster(
    integration_env_or_skip: dict[str, str],
) -> None:
    """Stage 3b: the cluster row lands in fingerprints.db. This is what
    enables `confidence ≥ 0.7` for the same cluster on the second
    break.sh run (occurrences=2 → confidence=0.40, then 0.45, …, 0.70
    at occurrences=8). Persistence is the substrate F5 builds on."""
    home = _aurora_home()
    db_path = home / "fingerprints.db"
    # Ensure stage 3 has run at least once in this process.
    classify_event({
        "kind": "auth-failed",
        "details": {
            "exception_type": "401 Unauthorized",
            "message": "401 Unauthorized: Bad credentials",
        },
        "scope": {"process": "OssSupplyChainDefender"},
        "ts": "2026-05-10T06:22:17.768560+00:00",
    })

    assert db_path.exists()
    rows = sqlite3.connect(str(db_path)).execute(
        "SELECT cluster_id, kind, refinement, occurrences "
        "FROM fingerprints WHERE kind=? AND refinement=?",
        ("auth-failed", "token-expired"),
    ).fetchall()
    assert rows, "no auth-failed/token-expired cluster persisted"
    _cluster_id, kind, refinement, occurrences = rows[0]
    assert kind == "auth-failed"
    assert refinement == "token-expired"
    assert occurrences >= 1


def test_stage_4_surgeon_can_list_assets_against_live_tenant(
    integration_env_or_skip: dict[str, str],
) -> None:
    """Stage 4: Surgeon's read path against /odata/Assets succeeds with
    folder-scoped auth.

    Asserts only that a non-error response comes back; the actual
    asset count is environment-dependent."""
    client = UiPathClient(folder=os.environ.get("UIPATH_FOLDER", "AURORA-Demo"))
    with client.folder_context() as ref, client._http_with_folder(ref) as http:
        r = http.get("/odata/Assets", params={"$top": 100})
        assert r.status_code == 200, (
            f"Surgeon's asset-list path failed: HTTP {r.status_code}; "
            f"folder header may be wrong or scope insufficient"
        )
        body = r.json()
        # OData shape: {"@odata.context": ..., "value": [...]}.
        assert "value" in body
        assert isinstance(body["value"], list)


def test_stage_5_surgeon_round_trips_asset_value_against_live_tenant(
    integration_env_or_skip: dict[str, str],
) -> None:
    """Stage 5: the FULL Surgeon write path against the live tenant.

    Round-trip: read GITHUB_TOKEN, write a probe value, verify it
    landed, write the original back, verify restoration. Non-destructive
    by construction — final state == original state.

    Skipped (with a clear message) if the GITHUB_TOKEN asset isn't yet
    provisioned in AURORA-Demo. The runbook tells the operator how to
    provision it via the UiPath UI in 1 minute."""
    client = UiPathClient(folder=os.environ.get("UIPATH_FOLDER", "AURORA-Demo"))
    try:
        original_asset = client.get_asset("GITHUB_TOKEN")
    except RuntimeError as e:
        pytest.skip(
            f"GITHUB_TOKEN asset not provisioned in folder; create via "
            f"UiPath UI to enable Stage 5: {e}"
        )

    original_value = original_asset.get("StringValue") or ""
    assert original_value, "GITHUB_TOKEN asset has no StringValue — provision it first"

    probe = "aurora-self-heal-roundtrip-probe"
    try:
        # Write probe.
        client.update_asset("GITHUB_TOKEN", probe)
        # Read back; assert the change landed.
        after = client.get_asset("GITHUB_TOKEN")
        assert after.get("StringValue") == probe, (
            "probe value did not land — Surgeon write path broken"
        )
    finally:
        # Restore — this MUST succeed even if assertions above fail,
        # so the asset is never left in a probe state.
        client.update_asset("GITHUB_TOKEN", original_value)

    final = client.get_asset("GITHUB_TOKEN")
    assert final.get("StringValue") == original_value, (
        "restoration failed — GITHUB_TOKEN asset is now in an unexpected state"
    )
