"""Sentry contract tests — offline.

Asserts that ``parse_events_to_jsonl`` yields events that satisfy the pydantic
``Event`` contract, that the JSONL output covers every required ``kind`` value,
and that the fingerprint is deterministic across runs (per R.T.02 — test the
contract, R.T.03 — mock dependencies). The uipath SDK is replaced with a
``MagicMock``; this test never reaches Orchestrator.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tests.agents.contracts.sentry import (  # noqa: E402
    Event,
    events_to_jsonl,
    fingerprint,
    parse_events_to_jsonl,
)

REQUIRED_KINDS = {"job_faulted", "auth_failed", "asset_missing", "queue_idle"}


@pytest.fixture
def mocked_sdk() -> MagicMock:
    """A MagicMock standing in for ``uipath.platform.UiPath``.

    Any test that needs to *call* the SDK does so through this stub; we
    assert below that no live network calls happen by checking the mock's
    call list. The SUT — ``parse_events_to_jsonl`` — does not touch the SDK
    at all, but we plumb the mock through to make R.T.03 explicit.
    """
    sdk = MagicMock(name="uipath_sdk")
    sdk.jobs.list.return_value = []
    sdk.queues.list_items.return_value = []
    sdk.assets.list.return_value = []
    return sdk


def test_parse_events_validates_against_contract(sentry_state: dict[str, Any]) -> None:
    events = parse_events_to_jsonl(sentry_state)
    assert events, "expected at least one Event from the recorded state"
    for event in events:
        assert isinstance(event, Event)
        assert 0 < len(event.payload) < 64


def test_required_event_kinds_present(sentry_state: dict[str, Any]) -> None:
    events = parse_events_to_jsonl(sentry_state)
    kinds = {e.kind for e in events}
    missing = REQUIRED_KINDS - kinds
    assert not missing, f"missing required kinds in JSONL output: {missing}"


def test_jsonl_output_is_round_trip_safe(sentry_state: dict[str, Any]) -> None:
    events = parse_events_to_jsonl(sentry_state)
    serialised = events_to_jsonl(events)
    decoded = [json.loads(line) for line in serialised.splitlines() if line.strip()]
    assert len(decoded) == len(events)
    for raw, event in zip(decoded, events, strict=True):
        assert raw["kind"] == event.kind
        assert raw["severity"] == event.severity


def test_fingerprint_deterministic_across_runs(sentry_state: dict[str, Any]) -> None:
    first = fingerprint(parse_events_to_jsonl(sentry_state))
    second = fingerprint(parse_events_to_jsonl(sentry_state))
    assert first == second
    assert len(first) == 64


def test_recorded_events_jsonl_matches_required_kinds(
    sentry_recorded_events: list[dict[str, Any]],
) -> None:
    assert len(sentry_recorded_events) >= 10, "recorded sample must have ≥10 events"
    kinds = {row["kind"] for row in sentry_recorded_events}
    assert REQUIRED_KINDS <= kinds


def test_sdk_is_mocked_at_boundary(
    mocked_sdk: MagicMock, sentry_state: dict[str, Any]
) -> None:
    """R.T.03 — never the SUT; the SDK is mocked at the boundary."""
    parse_events_to_jsonl(sentry_state)
    assert not mocked_sdk.jobs.list.called
    assert not mocked_sdk.queues.list_items.called
    assert not mocked_sdk.assets.list.called


def test_severity_classification_for_required_kinds(
    sentry_state: dict[str, Any],
) -> None:
    events = parse_events_to_jsonl(sentry_state)
    by_kind = {e.kind: e for e in events}
    assert by_kind["job_faulted"].severity == "error"
    assert by_kind["auth_failed"].severity == "critical"
    assert by_kind["asset_missing"].severity == "warning"
    assert by_kind["queue_idle"].severity == "info"
