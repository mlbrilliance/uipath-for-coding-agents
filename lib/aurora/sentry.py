"""Sentry daemon — continuously polls Orchestrator and emits events.

Runs as a long-lived asyncio loop. Reads policy.yaml::operate.sentry,
polls jobs/queues/assets/robots/Maestro instances per the configured
interval, and appends structured events to ${AURORA_HOME}/events.jsonl.

Diagnostician consumes the JSONL by tailing it (watchfiles).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from datetime import UTC, datetime

from aurora.fingerprint import classify_event
from aurora.memory import MemoryStore
from aurora.policy import load_policy
from aurora.uipath_client import UiPathClient

logger = logging.getLogger(__name__)


class Sentry:
    def __init__(
        self,
        *,
        client: UiPathClient | None = None,
        store: MemoryStore | None = None,
        interval_seconds: int | None = None,
    ):
        self.policy, _ = load_policy()
        self.client = client or UiPathClient(folder=self.policy.folder)
        self.store = store or MemoryStore()
        self.interval = int(interval_seconds or self.policy.operate["sentry"]["poll_interval_seconds"])
        self.events_path = self.store.home / "events.jsonl"
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        logger.info("sentry: starting; folder=%s interval=%ss", self.policy.folder, self.interval)
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:
                logger.exception("sentry: tick failed: %s", exc)
                self._emit({
                    "ts": _now_iso(),
                    "kind": "sentry_self_error",
                    "scope": {},
                    "details": {"message": str(exc)},
                })
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except TimeoutError:
                pass
        logger.info("sentry: stopped")

    async def _tick(self) -> None:
        # Run synchronous SDK calls in a thread to keep the loop responsive
        loop = asyncio.get_running_loop()
        failed = await loop.run_in_executor(None, self.client.list_failed_jobs, 5)
        for job in failed:
            self._emit_job_fault(job)

        # Maestro instances — only if the SDK exposes the endpoint
        try:
            faulted = await loop.run_in_executor(
                None,
                lambda: self.client.list_maestro_instances(state="Faulted"),
            )
            for inst in faulted:
                self._emit_maestro_fault(inst)
        except Exception:
            pass  # endpoint may not be available in older tenants

    # ---------- emitters ----------

    def _emit(self, event: dict) -> None:
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, separators=(",", ":")) + "\n")
        # Cluster on the way through so Diagnostician can read fingerprints later
        if event.get("kind", "").endswith("_failed") or event.get("kind", "").endswith("_faulted"):
            try:
                classify_event(event)
            except Exception:
                logger.exception("sentry: classify_event failed for %s", event.get("kind"))

    def _emit_job_fault(self, job: dict) -> None:
        self._emit({
            "ts": _now_iso(),
            "kind": "job_failed",
            "scope": {
                "folder": self.policy.folder,
                "process": job.get("ReleaseName"),
                "job_id": job.get("Id"),
            },
            "details": {
                "exception_type": (job.get("Info") or "").split(":", 1)[0],
                "message": job.get("Info", ""),
                "step": job.get("HostMachineName"),
                "started_at": job.get("StartTime"),
                "ended_at": job.get("EndTime"),
            },
        })

    def _emit_maestro_fault(self, inst: dict) -> None:
        self._emit({
            "ts": _now_iso(),
            "kind": "maestro_instance_faulted",
            "scope": {
                "folder": self.policy.folder,
                "process": inst.get("processName"),
                "instance_id": inst.get("id"),
            },
            "details": {
                "fault_step": inst.get("currentTask"),
                "message": inst.get("errorMessage", ""),
            },
        })


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---------- entrypoint ----------

async def main_async() -> int:
    logging.basicConfig(level=os.environ.get("AURORA_LOG_LEVEL", "INFO"))
    sentry = Sentry()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, sentry.stop)

    await sentry.run()
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
