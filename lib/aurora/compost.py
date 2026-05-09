"""Nightly compost step — turn accumulated learnings into HITL-gated skill PRs.

The compost loop reads the day's learnings JSONL (one record per agent action),
clusters them, filters by recurrence/cross-project thresholds, and for each
surviving cluster opens a GitHub PR against THIS repo's `skills/<name>/SKILL.md`
(or any other path the cluster recommends). Every PR is HITL-gated via
`aurora-promote` with `kind: skill_compost_pr` and is **never auto-merged**.

Discipline references:
    - R.SW.05 — HITL gates from policy.yaml are absolute
    - R.G.05  — compost-step skill PRs are NEVER auto-merged
    - R.X.03  — never store secrets in memory or learnings

Module seam:
    Higher-level orchestrators (Sonnet via the Conductor) generate the actual
    unified diff that updates a SKILL.md. This module accepts that diff
    pre-composed on the `Cluster` input. When no diff is supplied — the typical
    in-process call from the CLI/MCP entry points — this module emits a
    placeholder TODO diff so the surrounding plumbing (clustering, gating,
    PR creation) is exercised end-to-end. Replacing the placeholder with a
    real model-generated diff is out of scope for T-B3 (tracked separately).

Public surface:
    - LearningEntry, Cluster, PrResult — pydantic models
    - propose_skill_pr(...) — orchestrates the loop end-to-end
    - _filter_clusters_by_threshold, _compose_pr_body, _run_gh_pr_create — pure
      helpers, individually unit-testable.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


PR_TITLE_PREFIX = "[compost]"
GATE_KIND = "skill_compost_pr"


# ---------- Models ----------


class LearningEntry(BaseModel):
    """One line of `.aurora/learnings/<date>.jsonl`.

    Tolerant of optional fields — older entries may lack `skill` or `context`.
    """

    id: Optional[str] = None
    timestamp: str = Field(default="")
    agent: str = ""
    skill: str = ""
    project: str = ""
    kind: str = ""
    message: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class Cluster(BaseModel):
    """A group of learnings that recurs enough to warrant a skill update."""

    cluster_id: str
    occurrences: int
    projects: list[str]
    agents: list[str]
    recommended_skill_path: str  # e.g. "skills/aurora-fingerprint/SKILL.md"
    proposed_diff: str = ""  # unified diff body; may be a TODO placeholder
    reason: str = ""

    @property
    def skill_name(self) -> str:
        """Extract the skill name from `recommended_skill_path`."""
        # Path is e.g. "skills/aurora-fingerprint/SKILL.md"
        parts = Path(self.recommended_skill_path).parts
        if len(parts) >= 2 and parts[0] == "skills":
            return parts[1]
        return Path(self.recommended_skill_path).stem


PrState = Literal["opened", "gate-pending", "gate-approved", "merged", "closed", "dry-run"]


class PrResult(BaseModel):
    """Outcome of one compost-step proposal."""

    pr_url: str = ""
    branch_name: str = ""
    diff_files: list[str] = Field(default_factory=list)
    gate_task_id: str = ""  # Action Center task id from aurora-promote
    state: PrState = "opened"
    cluster_id: str = ""
    title: str = ""


# ---------- Public entry point ----------


def propose_skill_pr(
    learnings_path: Path,
    *,
    threshold_occurrences: int = 3,
    threshold_projects: int = 2,
    dry_run: bool = False,
    open_gate: Optional[Callable[..., Any]] = None,
    run_subprocess: Optional[Callable[..., subprocess.CompletedProcess[str]]] = None,
    diff_provider: Optional[Callable[[Cluster], str]] = None,
) -> list[PrResult]:
    """Run the compost loop over a learnings JSONL file.

    Steps:
        1. Load learnings JSONL — one ``LearningEntry`` per line.
        2. Cluster by ``aurora.fingerprint.cluster_learnings`` if it exists,
           else fall back to a (skill, kind) tuple grouping.
        3. Filter clusters by the recurrence + cross-project thresholds.
        4. For each surviving cluster, ensure a unified diff is attached
           (caller-supplied via ``diff_provider`` or the cluster itself; else
           a placeholder TODO diff).
        5. For non-dry-run clusters: route through ``aurora.promote.open_gate``
           with ``kind=skill_compost_pr``, then open a PR via ``gh pr create``.
        6. Return one ``PrResult`` per cluster.

    Args:
        learnings_path: Path to the JSONL file. Missing path -> empty list.
        threshold_occurrences: Minimum occurrences to keep a cluster.
        threshold_projects: Minimum distinct projects.
        dry_run: When True, skip the gate + ``gh pr create``; just return
            candidates with ``state="dry-run"``.
        open_gate: Override for ``aurora.promote.open_gate`` (used in tests).
        run_subprocess: Override for ``subprocess.run`` (used in tests).
        diff_provider: Optional callable that returns a unified diff for a
            cluster — used to plug in a Sonnet-generated diff later.
    """
    learnings = list(_load_learnings(learnings_path))
    if not learnings:
        logger.info("compost: no learnings at %s", learnings_path)
        return []

    clusters = _cluster_learnings(learnings)
    survivors = _filter_clusters_by_threshold(
        clusters,
        threshold_occurrences=threshold_occurrences,
        threshold_projects=threshold_projects,
    )

    results: list[PrResult] = []
    for cluster in survivors:
        # Attach a diff: caller-provided > cluster-supplied > placeholder.
        if diff_provider is not None:
            cluster.proposed_diff = diff_provider(cluster) or cluster.proposed_diff
        if not cluster.proposed_diff:
            cluster.proposed_diff = _placeholder_diff(cluster)

        if dry_run:
            results.append(
                PrResult(
                    cluster_id=cluster.cluster_id,
                    state="dry-run",
                    title=_compose_pr_title(cluster),
                    diff_files=[cluster.recommended_skill_path],
                )
            )
            continue

        gate_fn = open_gate or _default_open_gate
        gate_task_id = _open_compost_gate(cluster, gate_fn)

        runner = run_subprocess or subprocess.run
        pr_url, branch = _run_gh_pr_create(cluster, gate_task_id, runner=runner)

        results.append(
            PrResult(
                pr_url=pr_url,
                branch_name=branch,
                diff_files=[cluster.recommended_skill_path],
                gate_task_id=gate_task_id,
                state="gate-pending",
                cluster_id=cluster.cluster_id,
                title=_compose_pr_title(cluster),
            )
        )

    logger.info("compost: %d cluster(s) processed (dry_run=%s)", len(results), dry_run)
    return results


# ---------- Helpers (pure, testable) ----------


def _load_learnings(path: Path) -> Iterable[LearningEntry]:
    """Yield one LearningEntry per JSONL line; skip malformed lines."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("compost: skipping malformed JSONL line in %s", path)
            continue
        # Tolerate alternate field names from older schema variants.
        record.setdefault("project", record.get("project_id", ""))
        record.setdefault("message", record.get("summary", ""))
        record.setdefault("timestamp", record.get("ts", ""))
        try:
            yield LearningEntry(**{
                k: v for k, v in record.items()
                if k in LearningEntry.model_fields
            })
        except Exception as e:  # noqa: BLE001
            logger.warning("compost: invalid learning record (%s): %s", e, record)


def _cluster_learnings(learnings: list[LearningEntry]) -> list[Cluster]:
    """Cluster learnings, preferring fingerprint.cluster_learnings if present."""
    try:
        from aurora.fingerprint import cluster_learnings as fp_cluster  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        fp_cluster = None  # type: ignore[assignment]

    if fp_cluster is not None:
        try:
            return list(fp_cluster(learnings))
        except Exception:  # noqa: BLE001
            logger.warning("compost: fingerprint.cluster_learnings raised; using fallback", exc_info=True)

    return _fallback_cluster(learnings)


def _fallback_cluster(learnings: list[LearningEntry]) -> list[Cluster]:
    """Group by (skill, kind); collect projects + agents per group."""
    grouped: dict[tuple[str, str], list[LearningEntry]] = defaultdict(list)
    for entry in learnings:
        key = (entry.skill or "unknown-skill", entry.kind or "unknown-kind")
        grouped[key].append(entry)

    clusters: list[Cluster] = []
    for (skill, kind), entries in grouped.items():
        projects = sorted({e.project for e in entries if e.project})
        agents = sorted({e.agent for e in entries if e.agent})
        sample_messages = [e.message for e in entries[:3] if e.message]
        reason = (
            f"{len(entries)} occurrence(s) of kind={kind!r} in skill={skill!r} "
            f"across {len(projects)} project(s)"
        )
        if sample_messages:
            reason += f"; sample: {sample_messages[0][:160]}"

        # Recommend the SKILL.md path under skills/<skill>/.
        recommended_path = (
            f"skills/{skill}/SKILL.md" if skill != "unknown-skill" else "skills/UNKNOWN/SKILL.md"
        )
        clusters.append(
            Cluster(
                cluster_id=f"{skill}::{kind}",
                occurrences=len(entries),
                projects=projects,
                agents=agents,
                recommended_skill_path=recommended_path,
                proposed_diff="",
                reason=reason,
            )
        )
    return clusters


def _filter_clusters_by_threshold(
    clusters: list[Cluster],
    *,
    threshold_occurrences: int,
    threshold_projects: int,
) -> list[Cluster]:
    """Keep clusters with enough occurrences AND enough distinct projects."""
    return [
        c for c in clusters
        if c.occurrences >= threshold_occurrences
        and len(c.projects) >= threshold_projects
    ]


def _compose_pr_title(cluster: Cluster) -> str:
    return f"{PR_TITLE_PREFIX} propose skill update for {cluster.skill_name}"


def _compose_pr_body(cluster: Cluster, gate_task_id: str) -> str:
    """Cluster summary + proposed diff + gate context + rollback runbook.

    Tested in test_compose_pr_body_includes_required_sections.
    """
    gate_line = (
        f"Action Center task id: `{gate_task_id}` (kind: `{GATE_KIND}`)."
        if gate_task_id
        else "Action Center task: pending creation."
    )
    projects_md = ", ".join(f"`{p}`" for p in cluster.projects) or "(none)"
    agents_md = ", ".join(f"`{a}`" for a in cluster.agents) or "(none)"

    return (
        f"# Compost-step skill update\n\n"
        f"## Cluster summary\n\n"
        f"- Cluster: `{cluster.cluster_id}`\n"
        f"- Occurrences: **{cluster.occurrences}** across {len(cluster.projects)} project(s)\n"
        f"- Projects: {projects_md}\n"
        f"- Agents: {agents_md}\n"
        f"- Reason: {cluster.reason or '(none)'}\n\n"
        f"## Proposed diff\n\n"
        f"```diff\n{cluster.proposed_diff or '(no diff supplied)'}\n```\n\n"
        f"## Policy gate\n\n"
        f"This PR is HITL-gated via `aurora-promote` and is **never auto-merged**.\n"
        f"{gate_line}\n\n"
        f"## Rollback runbook\n\n"
        f"1. If approved by mistake: `git revert <merge-sha>` and push to a new branch.\n"
        f"2. Re-open the cluster for review by appending a learning with "
        f"`kind=compost-rollback` and `cluster_id={cluster.cluster_id}`.\n"
        f"3. The next compost run will re-evaluate with the rollback signal.\n"
    )


def _placeholder_diff(cluster: Cluster) -> str:
    """A TODO unified diff used when no real diff is supplied.

    Documents the seam: a higher-level orchestrator (Sonnet via Task()) is
    expected to replace this with a real generated diff. Keeping the
    placeholder ensures the rest of the pipeline (gate + PR open) can be
    exercised end-to-end without that orchestrator wired up.
    """
    return (
        f"--- a/{cluster.recommended_skill_path}\n"
        f"+++ b/{cluster.recommended_skill_path}\n"
        f"@@ TODO @@\n"
        f"+ <!-- compost: pattern observed in cluster {cluster.cluster_id} "
        f"({cluster.occurrences} occurrences across {len(cluster.projects)} projects). "
        f"Replace this placeholder with a model-generated update. -->\n"
    )


def _branch_name(cluster: Cluster) -> str:
    """Stable branch name per cluster + day."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe = cluster.cluster_id.replace("::", "-").replace("/", "-")
    return f"compost/{today}/{safe}"


def _default_open_gate(**kwargs: Any) -> Any:
    """Lazy import wrapper around aurora.promote.open_gate."""
    from aurora.promote import open_gate as _gate

    return _gate(**kwargs)


def _open_compost_gate(cluster: Cluster, gate_fn: Callable[..., Any]) -> str:
    """Route the cluster through aurora-promote; return the task id."""
    response = gate_fn(
        kind=GATE_KIND,
        candidate=cluster.cluster_id,
        context={
            "cluster_id": cluster.cluster_id,
            "occurrences": cluster.occurrences,
            "projects": cluster.projects,
            "skill_path": cluster.recommended_skill_path,
            "reason": cluster.reason,
        },
        approvers_env="AURORA_COMPOST_APPROVERS",
    )
    # Tolerate both GateResponse-like objects and dicts (test fakes).
    task_id = getattr(response, "task_id", None)
    if task_id is None and isinstance(response, dict):
        task_id = response.get("task_id")
    return str(task_id) if task_id is not None else ""


def _run_gh_pr_create(
    cluster: Cluster,
    gate_task_id: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> tuple[str, str]:
    """Invoke `gh pr create` for a cluster. Returns (pr_url, branch_name).

    Note R.G.05: NO `--merge` or `-m` flag is ever passed. Compost PRs are
    HITL-gated and must not be auto-merged.
    """
    branch = _branch_name(cluster)
    title = _compose_pr_title(cluster)
    body = _compose_pr_body(cluster, gate_task_id)

    base = os.environ.get("AURORA_COMPOST_BASE_BRANCH", "main")
    cmd = [
        "gh", "pr", "create",
        "--title", title,
        "--body", body,
        "--head", branch,
        "--base", base,
        "--draft",
    ]

    logger.info("compost: opening PR for cluster=%s", cluster.cluster_id)
    completed = runner(cmd, capture_output=True, text=True, check=False)

    pr_url = ""
    stdout = (getattr(completed, "stdout", "") or "").strip()
    if stdout:
        # `gh pr create` prints the URL on stdout.
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("http"):
                pr_url = line
                break
        if not pr_url:
            pr_url = stdout.splitlines()[-1].strip()

    rc = getattr(completed, "returncode", 0)
    if rc != 0:
        logger.warning(
            "compost: gh pr create exited rc=%s stderr=%s",
            rc,
            getattr(completed, "stderr", ""),
        )
    return pr_url, branch
