"""Three-tier memory store for AURORA.

Tiers:
    - project: per-bot artifacts under .aurora/projects/<id>/
    - org:     cumulative patterns under .aurora/org/
    - skill:   one-line learnings + fingerprint index under .aurora/learnings/ + fingerprints.db

Public surface:
    - MemoryStore(home).read(tier, ...)
    - MemoryStore(home).append_learning(...)
    - MemoryStore(home).iter_learnings(since=...)
    - MemoryStore(home).search_org(query, limit, fleet)

Direct file I/O is allowed within an agent's own scope; cross-scope access
should go through `aurora.recall` for ranking and audit.
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Learning:
    ts: str
    agent: str
    project_id: str
    kind: str
    summary: str
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MemorySlice:
    path: str
    snippet: str
    score: float = 0.0
    ts: str | None = None
    tier: str = ""


class MemoryStore:
    def __init__(self, home: Path | None = None):
        self.home = Path(home or os.environ.get("AURORA_HOME", "/opt/aurora"))
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "projects").mkdir(exist_ok=True)
        (self.home / "org").mkdir(exist_ok=True)
        (self.home / "learnings").mkdir(exist_ok=True)
        (self.home / "triage").mkdir(exist_ok=True)
        (self.home / "audit").mkdir(exist_ok=True)
        (self.home / "archive").mkdir(exist_ok=True)
        (self.home / "runs").mkdir(exist_ok=True)
        (self.home / "deprecation").mkdir(exist_ok=True)

    # ---------- project tier ----------

    def project_dir(self, project_id: str) -> Path:
        d = self.home / "projects" / project_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def read_project_artifact(self, project_id: str, name: str) -> str | None:
        p = self.project_dir(project_id) / name
        return p.read_text(encoding="utf-8") if p.exists() else None

    def write_project_artifact(self, project_id: str, name: str, content: str) -> Path:
        p = self.project_dir(project_id) / name
        p.write_text(content, encoding="utf-8")
        return p

    # ---------- org tier ----------

    def read_org_doc(self, name: str) -> str | None:
        p = self.home / "org" / name
        return p.read_text(encoding="utf-8") if p.exists() else None

    def append_org_doc(self, name: str, line: str) -> None:
        p = self.home / "org" / name
        with p.open("a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")

    def search_org(self, query: str, *, limit: int = 10, fleet: str | None = None) -> list[MemorySlice]:
        """Naive grep + TF-IDF-ish relevance over org markdown files."""
        terms = [t for t in re.findall(r"\w{3,}", query.lower())]
        results: list[MemorySlice] = []
        for p in (self.home / "org").rglob("*.md"):
            text = p.read_text(encoding="utf-8")
            if fleet and f"fleet:{fleet}" not in text and f"fleet: {fleet}" not in text:
                # Org docs may carry an optional "fleet:" front-matter line; if missing, treat as cross-fleet (score 0.5)
                pass
            score = sum(text.lower().count(t) for t in terms)
            if score == 0:
                continue
            # snippet around best match
            best = _best_snippet(text, terms)
            results.append(MemorySlice(
                path=str(p.relative_to(self.home.parent if self.home.parent.exists() else self.home)),
                snippet=best,
                score=score,
                tier="org",
            ))
        results.sort(key=lambda s: s.score, reverse=True)
        return results[:limit]

    # ---------- skill tier (learnings) ----------

    def append_learning(
        self,
        *,
        agent: str,
        project_id: str,
        kind: str,
        summary: str,
        ts: str | None = None,
        raw: dict | None = None,
    ) -> Path:
        ts = ts or datetime.now(UTC).isoformat()
        date = ts.split("T")[0]
        path = self.home / "learnings" / f"{date}.jsonl"
        record = {
            "ts": ts,
            "agent": agent,
            "project_id": project_id,
            "kind": kind,
            "summary": summary,
            "raw": raw or {},
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
        return path

    def iter_learnings(self, *, since: timedelta | None = None) -> Iterator[Learning]:
        cutoff: datetime | None = None
        if since:
            cutoff = datetime.now(UTC) - since
        for p in sorted((self.home / "learnings").glob("*.jsonl")):
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if cutoff:
                    try:
                        rec_ts = datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
                        if rec_ts < cutoff:
                            continue
                    except (KeyError, ValueError):
                        continue
                yield Learning(
                    ts=record["ts"],
                    agent=record.get("agent", "unknown"),
                    project_id=record.get("project_id", ""),
                    kind=record.get("kind", ""),
                    summary=record.get("summary", ""),
                    raw=record.get("raw", {}),
                )

    # ---------- backlog ----------

    def backlog_path(self) -> Path:
        return self.home.parent / ".aurora" / "backlog.md" if (self.home.parent / ".aurora").exists() else self.home / "backlog.md"

    def read_backlog(self) -> str:
        p = self.backlog_path()
        return p.read_text(encoding="utf-8") if p.exists() else "# AURORA Backlog\n"

    def write_backlog(self, content: str) -> None:
        self.backlog_path().write_text(content, encoding="utf-8")


def _best_snippet(text: str, terms: list[str], radius: int = 80) -> str:
    if not terms:
        return text[:160]
    lower = text.lower()
    best_idx = -1
    best_term = ""
    for t in terms:
        idx = lower.find(t)
        if idx >= 0 and (best_idx < 0 or idx < best_idx):
            best_idx = idx
            best_term = t
    if best_idx < 0:
        return text[:160]
    start = max(0, best_idx - radius)
    end = min(len(text), best_idx + len(best_term) + radius)
    return ("…" if start > 0 else "") + text[start:end].strip() + ("…" if end < len(text) else "")
