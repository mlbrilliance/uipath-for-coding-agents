"""Unit tests for aurora.compost.

Covers:
    - _filter_clusters_by_threshold (recurrence + cross-project gates)
    - _compose_pr_body (PR body has all required sections)
    - propose_skill_pr (routes through aurora.promote, dry-run skips gh,
      real run calls gh with the right shape, NO auto-merge flag).
    - aurora_compost_dry_run MCP tool returns candidates, not a stub.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from aurora import compost
from aurora.compost import (
    Cluster,
    LearningEntry,
    PrResult,
    _compose_pr_body,
    _compose_pr_title,
    _filter_clusters_by_threshold,
    propose_skill_pr,
)


# ---------- helpers ----------


def _make_cluster(
    *,
    occurrences: int = 5,
    projects: list[str] | None = None,
    cluster_id: str = "aurora-fingerprint::selector-broken",
    skill_path: str = "skills/aurora-fingerprint/SKILL.md",
) -> Cluster:
    return Cluster(
        cluster_id=cluster_id,
        occurrences=occurrences,
        projects=projects if projects is not None else ["proj-a", "proj-b"],
        agents=["surgeon"],
        recommended_skill_path=skill_path,
        proposed_diff="",
        reason="recurring selector-broken pattern",
    )


def _write_learnings(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


# ---------- _filter_clusters_by_threshold ----------


def test_filter_clusters_keeps_above_threshold() -> None:
    above = _make_cluster(occurrences=4, projects=["p1", "p2"])
    out = _filter_clusters_by_threshold(
        [above], threshold_occurrences=3, threshold_projects=2
    )
    assert out == [above]


def test_filter_clusters_drops_below_threshold() -> None:
    too_few_occ = _make_cluster(occurrences=2, projects=["p1", "p2"])
    too_few_proj = _make_cluster(
        occurrences=10, projects=["p1"], cluster_id="other::kind"
    )
    survivor = _make_cluster(occurrences=3, projects=["p1", "p2"])
    out = _filter_clusters_by_threshold(
        [too_few_occ, too_few_proj, survivor],
        threshold_occurrences=3,
        threshold_projects=2,
    )
    assert out == [survivor]


# ---------- _compose_pr_body ----------


def test_compose_pr_body_includes_required_sections() -> None:
    cluster = _make_cluster()
    cluster.proposed_diff = "--- a/skills/x/SKILL.md\n+++ b/skills/x/SKILL.md\n+ note\n"
    body = _compose_pr_body(cluster, gate_task_id="task-42")

    assert "## Cluster summary" in body
    assert "## Proposed diff" in body
    assert "## Policy gate" in body
    assert "## Rollback runbook" in body
    # Cluster identity threaded into the body
    assert cluster.cluster_id in body
    assert "task-42" in body
    assert "skill_compost_pr" in body
    # Diff is fenced
    assert "```diff" in body


# ---------- propose_skill_pr ----------


def _seed_learnings_for_one_cluster(path: Path) -> None:
    """Three occurrences across two projects, all targeting the same skill+kind."""
    _write_learnings(
        path,
        [
            {
                "id": "L1",
                "timestamp": "2026-05-09T01:00:00Z",
                "agent": "surgeon",
                "skill": "aurora-fingerprint",
                "project": "proj-a",
                "kind": "selector-broken",
                "message": "wnd-aaname-mismatch resolved by re-walking ariaName",
                "context": {},
            },
            {
                "id": "L2",
                "timestamp": "2026-05-09T02:00:00Z",
                "agent": "surgeon",
                "skill": "aurora-fingerprint",
                "project": "proj-a",
                "kind": "selector-broken",
                "message": "wnd-aaname-mismatch fixed",
                "context": {},
            },
            {
                "id": "L3",
                "timestamp": "2026-05-09T03:00:00Z",
                "agent": "surgeon",
                "skill": "aurora-fingerprint",
                "project": "proj-b",
                "kind": "selector-broken",
                "message": "wnd-aaname-mismatch fixed",
                "context": {},
            },
        ],
    )


def test_propose_skill_pr_routes_through_aurora_promote(tmp_path: Path) -> None:
    learnings = tmp_path / "2026-05-09.jsonl"
    _seed_learnings_for_one_cluster(learnings)

    gate_calls: list[dict[str, Any]] = []

    def fake_gate(**kwargs: Any) -> dict[str, Any]:
        gate_calls.append(kwargs)
        return {"task_id": 9999}

    def fake_run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="https://github.com/x/y/pull/1\n", stderr=""
        )

    results = propose_skill_pr(
        learnings,
        dry_run=False,
        open_gate=fake_gate,
        run_subprocess=fake_run,
    )

    assert results, "expected at least one cluster to survive thresholds"
    assert len(gate_calls) == 1
    assert gate_calls[0]["kind"] == compost.GATE_KIND == "skill_compost_pr"
    # The gate must receive cluster context (not just blank kwargs)
    ctx = gate_calls[0]["context"]
    assert "cluster_id" in ctx
    assert ctx["occurrences"] == 3
    # PrResult propagates the gate task id
    assert results[0].gate_task_id == "9999"
    assert results[0].state == "gate-pending"


def test_propose_skill_pr_dry_run_does_not_call_gh(tmp_path: Path) -> None:
    learnings = tmp_path / "2026-05-09.jsonl"
    _seed_learnings_for_one_cluster(learnings)

    gate_calls: list[Any] = []
    run_calls: list[Any] = []

    def fake_gate(**kwargs: Any) -> dict[str, Any]:
        gate_calls.append(kwargs)
        return {"task_id": 1}

    def fake_run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        run_calls.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    results = propose_skill_pr(
        learnings,
        dry_run=True,
        open_gate=fake_gate,
        run_subprocess=fake_run,
    )

    assert results, "dry_run should still surface candidate clusters"
    assert run_calls == [], "dry_run must not invoke gh pr create"
    assert gate_calls == [], "dry_run must not open the HITL gate"
    assert results[0].state == "dry-run"


def test_propose_skill_pr_real_run_calls_gh_with_correct_args(tmp_path: Path) -> None:
    learnings = tmp_path / "2026-05-09.jsonl"
    _seed_learnings_for_one_cluster(learnings)

    captured: list[list[str]] = []

    def fake_gate(**_kw: Any) -> dict[str, Any]:
        return {"task_id": 7}

    def fake_run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        captured.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="https://github.com/x/y/pull/2\n", stderr=""
        )

    results = propose_skill_pr(
        learnings,
        dry_run=False,
        open_gate=fake_gate,
        run_subprocess=fake_run,
    )

    assert captured, "expected gh pr create to be invoked"
    cmd = captured[0]
    assert cmd[:3] == ["gh", "pr", "create"]
    # Title shape
    title_idx = cmd.index("--title")
    title = cmd[title_idx + 1]
    assert title.startswith("[compost] propose skill update for ")
    # Body present and includes section headers
    body_idx = cmd.index("--body")
    body = cmd[body_idx + 1]
    assert "## Cluster summary" in body
    assert "## Proposed diff" in body
    # PR url propagated
    assert results[0].pr_url == "https://github.com/x/y/pull/2"


def test_no_auto_merge_in_pr_create_args(tmp_path: Path) -> None:
    """R.G.05: compost PRs are NEVER auto-merged. The gh invocation must
    not pass `--merge`, `-m`, `--auto`, or any equivalent."""
    learnings = tmp_path / "2026-05-09.jsonl"
    _seed_learnings_for_one_cluster(learnings)

    captured: list[list[str]] = []

    def fake_gate(**_kw: Any) -> dict[str, Any]:
        return {"task_id": 1}

    def fake_run(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        captured.append(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    propose_skill_pr(
        learnings, dry_run=False, open_gate=fake_gate, run_subprocess=fake_run
    )

    assert captured, "gh pr create must have been called"
    cmd = captured[0]
    forbidden = {"--merge", "-m", "--auto", "--admin", "--squash", "--rebase"}
    bad = [t for t in cmd if t in forbidden]
    assert not bad, f"compost PR command leaked auto-merge flags: {bad}"


def test_propose_skill_pr_handles_missing_file(tmp_path: Path) -> None:
    """No learnings file -> empty list, no gate calls, no gh calls."""
    missing = tmp_path / "does-not-exist.jsonl"

    def boom(**_kw: Any) -> Any:
        raise AssertionError("gate must not be invoked when file is missing")

    def boom_run(cmd: list[str], **_kw: Any) -> Any:
        raise AssertionError("gh must not be invoked when file is missing")

    results = propose_skill_pr(
        missing, dry_run=False, open_gate=boom, run_subprocess=boom_run
    )
    assert results == []


def test_propose_skill_pr_filters_below_threshold(tmp_path: Path) -> None:
    """Single learning -> nothing proposed."""
    learnings = tmp_path / "2026-05-09.jsonl"
    _write_learnings(
        learnings,
        [
            {
                "timestamp": "2026-05-09T01:00:00Z",
                "agent": "surgeon",
                "skill": "aurora-fingerprint",
                "project": "proj-a",
                "kind": "one-off",
                "message": "single occurrence",
            }
        ],
    )

    def boom(**_kw: Any) -> Any:
        raise AssertionError("gate must not be invoked when nothing survives thresholds")

    def boom_run(cmd: list[str], **_kw: Any) -> Any:
        raise AssertionError("gh must not be invoked when nothing survives thresholds")

    results = propose_skill_pr(
        learnings, dry_run=False, open_gate=boom, run_subprocess=boom_run
    )
    assert results == []


# ---------- MCP wiring ----------


def test_mcp_aurora_compost_dry_run_returns_candidates_not_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The MCP tool used to return {"stub": True, ...}; now it must return
    a real `candidates` array fed by aurora.compost.propose_skill_pr."""
    from datetime import datetime, timezone

    from aurora.mcp.server import _dispatch

    home = tmp_path / "aurora-home"
    (home / "learnings").mkdir(parents=True)
    monkeypatch.setenv("AURORA_HOME", str(home))

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _seed_learnings_for_one_cluster(home / "learnings" / f"{date}.jsonl")

    result = asyncio.run(_dispatch("aurora_compost_dry_run", {"since_days": 1}))

    assert isinstance(result, dict)
    assert "candidates" in result
    assert "stub" not in result
    assert isinstance(result["candidates"], list)
    assert result["candidates"], "expected at least one candidate from seeded learnings"
    candidate = result["candidates"][0]
    assert candidate["state"] == "dry-run"
    assert candidate["title"].startswith("[compost]")
