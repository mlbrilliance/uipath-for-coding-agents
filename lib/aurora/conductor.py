"""Conductor — meta-orchestrator daemon for the AURORA swarm.

Two modes:
    - In-session (via Claude Code subagent invocation) — Conductor is just
      another agent that uses Task to dispatch to peers. The agent
      definition in `agents/conductor.md` drives that.
    - Daemon (long-running) — this module. Runs alongside Sentry, executes
      cron-style schedules (Auditor 02:00, Strategist 02:30, Compost 03:00),
      and coordinates the Operate fleet's reactive loop using the Claude
      Agent SDK with subscription OAuth.

This file implements the daemon. It uses the Claude Agent SDK so it can
spawn agent invocations even when no human Claude Code session is open.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from dataclasses import dataclass
from datetime import UTC, datetime

from aurora.memory import MemoryStore
from aurora.policy import AuroraPolicy, load_policy
from aurora.sentry import Sentry

logger = logging.getLogger(__name__)


@dataclass
class CronJob:
    name: str
    hour: int
    minute: int
    func: str  # name of an async coroutine on Conductor
    last_run: datetime | None = None


class Conductor:
    """Long-running supervisor.

    Owns:
      - the Sentry daemon
      - cron-style nightly tasks (Auditor, Strategist, Compost)
      - the worktree pool (lib placeholder for v1)
      - daily token-budget tracking
    """

    def __init__(self, *, policy: AuroraPolicy | None = None):
        self.policy: AuroraPolicy = policy or load_policy()[0]
        self.store = MemoryStore()
        self.sentry = Sentry()
        self._stop = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()
        self.crons: list[CronJob] = [
            CronJob(name="auditor_daily",   hour=2, minute=0,  func="run_auditor"),
            CronJob(name="strategist_nightly", hour=2, minute=30, func="run_strategist"),
            CronJob(name="compost_nightly", hour=3, minute=0,  func="run_compost"),
        ]
        self.token_budget_usd: float = float(self.policy.budget["daily_usd"])
        self.spent_today_usd: float = 0.0

    def stop(self) -> None:
        self._stop.set()
        self.sentry.stop()

    async def run(self) -> None:
        """Top-level loop: Sentry runs concurrently; cron tick fires every minute."""
        logger.info("conductor: starting; budget=$%.2f/day", self.token_budget_usd)
        sentry_task = asyncio.create_task(self.sentry.run(), name="sentry")
        cron_task = asyncio.create_task(self._cron_loop(), name="cron")
        try:
            await self._stop.wait()
        finally:
            self.sentry.stop()
            await asyncio.gather(sentry_task, cron_task, return_exceptions=True)
        logger.info("conductor: stopped")

    async def _cron_loop(self) -> None:
        while not self._stop.is_set():
            now = datetime.now(UTC)
            for job in self.crons:
                if (
                    now.hour == job.hour
                    and now.minute == job.minute
                    and (job.last_run is None or (now - job.last_run).total_seconds() > 300)
                ):
                    job.last_run = now
                    func = getattr(self, job.func, None)
                    if func is None:
                        logger.warning("cron: no method %s on Conductor", job.func)
                        continue
                    logger.info("cron: dispatching %s", job.name)
                    task = asyncio.create_task(_safe(func()))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60)
            except TimeoutError:
                pass

    # ---------- cron handlers ----------

    async def run_auditor(self) -> None:
        """Daily drift / license / deprecation scan via the Auditor subagent."""
        await _spawn_agent(
            agent="auditor",
            prompt=(
                "Run the daily audit pass. Compare deployed package hashes against the repo, "
                "reconcile license vs robot utilization, list deprecation candidates. "
                f"Folder: {self.policy.folder}. "
                "Write `.aurora/audit/<date>-drift.md` with findings."
            ),
        )

    async def run_strategist(self) -> None:
        """Nightly portfolio retrospective."""
        await _spawn_agent(
            agent="strategist",
            prompt=(
                "Run the nightly retrospective. Read org memory, the scored backlog, deployed-bot "
                "inventory, and last 90 days of execution telemetry. Recommend consolidations, "
                "deprecations, re-prioritizations, and skill-investment candidates. "
                f"Write `.aurora/strategy/{datetime.now(UTC).strftime('%Y-%m-%d')}.md`."
            ),
        )

    async def run_compost(self) -> None:
        """Nightly skill-update PR generation."""
        await _spawn_agent(
            agent="conductor",  # compost is a Conductor responsibility, not its own agent
            prompt=(
                "Run the compost step. Read today's `.aurora/learnings/<date>.jsonl`, cluster "
                "by skill, identify recurring patterns (>=3 occurrences across >=2 projects with "
                "consistent rationale), and open one or more GitHub PRs against `skills/` with "
                "the proposed updates. Each PR is HITL-gated via `aurora-promote` "
                "(kind: skill_compost_pr). NEVER auto-merge."
            ),
        )


async def _safe(coro) -> None:
    try:
        await coro
    except Exception:
        logger.exception("cron task failed")


async def _spawn_agent(*, agent: str, prompt: str) -> None:
    """Invoke a subagent via the Claude Agent SDK using subscription OAuth.

    The actual SDK call is feature-flagged so this module imports cleanly
    even if the SDK isn't installed yet (early bootstrap).
    """
    try:
        from claude_agent_sdk import query  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("claude-agent-sdk not installed; would have invoked agent=%s", agent)
        return

    logger.info("spawning agent %s", agent)
    # The SDK reads ~/.claude/credentials.json (subscription OAuth) by default.
    options = {"subagent": agent}
    async for event in query(prompt=prompt, options=options):  # type: ignore[arg-type]
        logger.debug("agent[%s] %s", agent, event)


# ---------- entrypoint ----------

async def main_async() -> int:
    logging.basicConfig(level=os.environ.get("AURORA_LOG_LEVEL", "INFO"))
    conductor = Conductor()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, conductor.stop)

    await conductor.run()
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
