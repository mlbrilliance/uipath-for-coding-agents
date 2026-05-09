"""Unit tests for aurora.fingerprint."""
from __future__ import annotations

from pathlib import Path

import pytest

from aurora import fingerprint


def test_message_skeleton_redacts_uuids_paths_urls() -> None:
    msg = (
        "selector <wnd app='chrome.exe' /> not found at "
        "https://example.com/some/path/abc-d44b-7c5e-9f01-002030405060 "
        "after 30000ms (workflow C:\\Users\\bob\\app.exe)"
    )
    skel = fingerprint.message_skeleton(msg)
    assert "<selector>" in skel
    assert "<url>" in skel
    # Either path or version may match the C:\... pattern; both are redactions.
    assert any(t in skel for t in ("<path>", "<version>"))


def test_canonical_kinds_complete() -> None:
    expected = {
        "selector-broken", "auth-failed", "external-api-drift",
        "null-arg", "timing", "data-quality", "network", "license",
    }
    assert fingerprint.CANONICAL_KINDS == expected


def test_derive_kind_selector(sample_event: dict) -> None:
    assert fingerprint.derive_kind(sample_event) == "selector-broken"


def test_derive_kind_auth() -> None:
    e = {
        "details": {
            "exception_type": "Octokit.HttpError",
            "message": "401 Bad credentials",
        }
    }
    assert fingerprint.derive_kind(e) == "auth-failed"


def test_derive_kind_unknown_returns_novel() -> None:
    e = {"details": {"exception_type": "SomeUnknownException", "message": "weird"}}
    assert fingerprint.derive_kind(e) == "novel-fault"


def test_derive_refinement_aaname_mismatch() -> None:
    refinement = fingerprint.derive_refinement(
        "selector-broken",
        "UiPath.Core.Activities.SelectorNotFoundException",
        "Could not find selector with aaname='Inbox'",
    )
    assert refinement == "aaname-mismatch"


def test_classify_event_creates_cluster_first_time(
    tmp_aurora_home: Path,
    sample_event: dict,
) -> None:
    result = fingerprint.classify_event(sample_event)
    assert result.kind == "selector-broken"
    assert result.refinement == "aaname-mismatch"
    assert result.size == 1
    assert result.novel is True


def test_classify_event_increments_on_recurrence(
    tmp_aurora_home: Path,
    sample_event: dict,
) -> None:
    fingerprint.classify_event(sample_event)
    fingerprint.classify_event(sample_event)
    result = fingerprint.classify_event(sample_event)
    assert result.size == 3
    assert result.novel is False
    assert result.confidence > 0.30


def test_append_resolution_attaches_pr(
    tmp_aurora_home: Path,
    sample_event: dict,
) -> None:
    initial = fingerprint.classify_event(sample_event)
    fingerprint.append_resolution(
        cluster_id=initial.cluster_id,
        pr="https://github.com/example/repo/pull/42",
        summary="Re-walked parent ariaName chain.",
    )
    next_classify = fingerprint.classify_event(sample_event)
    assert next_classify.prior_resolution is not None
    assert next_classify.prior_resolution["pr"].endswith("/pull/42")


def test_list_clusters_filters_by_kind(
    tmp_aurora_home: Path,
    sample_event: dict,
) -> None:
    fingerprint.classify_event(sample_event)
    auth_event = {
        "ts": "2026-05-09T04:00:00Z",
        "kind": "auth-failed",
        "details": {
            "exception_type": "Octokit.HttpError",
            "message": "401 Bad credentials",
            "step": "GitHub/FetchLockfile",
        },
    }
    fingerprint.classify_event(auth_event)
    selector_clusters = fingerprint.list_clusters(kind="selector-broken")
    auth_clusters = fingerprint.list_clusters(kind="auth-failed")
    assert len(selector_clusters) == 1
    assert len(auth_clusters) == 1
