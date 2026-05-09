"""Entry point for the AuroraMaintainerHealth Coded Agent (OpenAI Agents framework).

One function:
    main(input) — bulk maintainer-health lookup over a lockfiles batch
                  (called from the Maestro `MaintainerHealth` task).

The agent is built on the OpenAI Agents SDK (via `uipath-openai-agents`) with
two tools — `get_scorecard` and `get_commit_recency`. Tools live in
`tools/`, the system prompt lives in `prompts/triage.md`.

Scoring is deterministic: given the same lockfile batch and the same
upstream Scorecard / commit-recency answers, the report is byte-stable
(R.K.06). The LLM-driven Agent path is wired but only invoked when
runtime escalation is needed; the default bulk path stays in pure-Python
helpers so Tester can unit-test outside the OpenAI runtime.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Optional

import structlog
from agents import Agent, function_tool

from models import (
    Lockfile,
    LockfileEntry,
    MaintainerHealthInput,
    MaintainerHealthReport,
    PackageHealth,
)
from tools.commit_recency import CommitRecencyResult, get_commit_recency
from tools.scorecard import ScorecardResult, get_scorecard

logger = structlog.get_logger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "triage.md"


# ---------- Pure helpers (Tester targets these) ----------

def _flag_thresholds(
    scorecard_score: Optional[float],
    commit_recency_days: Optional[int],
) -> list[str]:
    """Derive risk flags from raw signal values.

    Rules (mirrored in `prompts/triage.md`):
    - `no-scorecard` when scorecard data is unavailable.
    - `low-scorecard` when score is known and < 4.0.
    - `stale` when commit recency exceeds ~18 months.
    """
    flags: list[str] = []
    if scorecard_score is None:
        flags.append("no-scorecard")
    elif scorecard_score < 4.0:
        flags.append("low-scorecard")
    if commit_recency_days is not None and commit_recency_days > 540:
        flags.append("stale")
    return flags


def _health_score(
    scorecard_score: Optional[float],
    commit_recency_days: Optional[int],
) -> float:
    """Combine scorecard + recency into a 0-10 health score."""
    base = 5.0 if scorecard_score is None else float(scorecard_score)
    if commit_recency_days is not None:
        if commit_recency_days > 540:
            base -= 3.0
        elif commit_recency_days > 365:
            base -= 1.5
    return max(0.0, min(10.0, base))


def _aggregate_health(packages: list[PackageHealth]) -> tuple[float, int]:
    """Compute (aggregate_score, flagged_count) for a list of PackageHealth."""
    if not packages:
        return (0.0, 0)
    aggregate = sum(p.health_score for p in packages) / len(packages)
    flagged = sum(1 for p in packages if p.flags)
    return (round(aggregate, 4), flagged)


# ---------- OpenAI Agents wiring ----------

@function_tool
async def scorecard_tool(repo_url: str) -> dict[str, Any]:
    """Return OpenSSF Scorecard data for the repo, or `found=False` if missing."""
    result: ScorecardResult = await get_scorecard(repo_url)
    return result.model_dump()


@function_tool
async def commit_recency_tool(repo_url: str) -> dict[str, Any]:
    """Return days since the latest commit on the default branch."""
    result: CommitRecencyResult = await get_commit_recency(repo_url)
    return result.model_dump()


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_agent() -> Agent:
    """Construct the OpenAI Agents-SDK Agent for runtime escalation paths."""
    return Agent(
        name="AuroraMaintainerHealth",
        instructions=_load_prompt(),
        tools=[scorecard_tool, commit_recency_tool],
    )


# ---------- Repo URL inference ----------

def _repo_url_for(dep: LockfileEntry) -> str:
    """Heuristic mapping from (ecosystem, name) → GitHub repo URL.

    A real-world implementation would consult package-registry metadata
    (npm `repository`, PyPI `project_urls`, Go module proxy). For the demo
    we synthesise a likely URL; the tool layer fails closed when the repo
    isn't found.
    """
    name = dep.name
    if dep.ecosystem == "go" and "/" in name and name.startswith("github.com/"):
        return f"https://{name}"
    if "/" in name:
        # npm scoped (`@org/pkg`) and similar: split on the first slash.
        owner, _, repo = name.partition("/")
        owner = owner.lstrip("@")
        return f"https://github.com/{owner}/{repo}"
    return f"https://github.com/{name}/{name}"


# ---------- Per-package evaluation ----------

async def _evaluate_package(dep: LockfileEntry) -> PackageHealth:
    """Fetch raw signals for one dependency and project them onto PackageHealth."""
    repo_url = _repo_url_for(dep)
    scorecard, recency = await asyncio.gather(
        get_scorecard(repo_url),
        get_commit_recency(repo_url),
    )
    scorecard_score = scorecard.score if scorecard.found else None
    commit_days = recency.days_since if recency.found else None
    return PackageHealth(
        ecosystem=dep.ecosystem,
        name=dep.name,
        version=dep.version,
        scorecard_score=scorecard_score,
        commit_recency_days=commit_days,
        health_score=_health_score(scorecard_score, commit_days),
        flags=_flag_thresholds(scorecard_score, commit_days),
    )


async def _run(batch: MaintainerHealthInput) -> MaintainerHealthReport:
    """Async core. `main()` is a thin sync shim over this."""
    deps = [dep for lf in batch.lockfiles for dep in lf.deps]
    packages = await asyncio.gather(*(_evaluate_package(d) for d in deps))
    aggregate, flagged = _aggregate_health(list(packages))
    return MaintainerHealthReport(
        packages=list(packages),
        aggregate_score=aggregate,
        flagged_count=flagged,
    )


# ---------- Maestro entry: MaintainerHealth task ----------

def main(input: dict[str, Any]) -> dict[str, Any]:
    """Bulk maintainer-health lookup over a lockfiles batch."""
    batch = MaintainerHealthInput.model_validate(input)
    logger.info(
        "maintainer-health.start",
        repos=len(batch.lockfiles),
        deps=sum(len(lf.deps) for lf in batch.lockfiles),
    )

    report = asyncio.run(_run(batch))

    logger.info(
        "maintainer-health.complete",
        packages=len(report.packages),
        aggregate=report.aggregate_score,
        flagged=report.flagged_count,
    )
    return report.model_dump()


if __name__ == "__main__":
    # Local debug: read input.json from the cwd and print output.
    import json
    import sys

    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("input.json")
    payload = json.loads(in_path.read_text())
    print(json.dumps(main(payload), indent=2))
