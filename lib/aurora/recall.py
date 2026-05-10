"""Scoped memory retrieval — the read side of `aurora.memory`.

Used by:
    - `pre-tool-load-memory.sh` hook (subprocess)
    - any agent that needs to look up prior context
    - the `/aurora-recall` slash command
    - the AURORA MCP server's `aurora_recall` tool
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aurora.fingerprint import list_clusters
from aurora.memory import MemorySlice, MemoryStore

logger = logging.getLogger(__name__)


# Default per-agent recall preferences (mirrors the table in skills/aurora-recall/SKILL.md)
AGENT_DEFAULTS: dict[str, dict] = {
    "scout":         {"tiers": [],                "fleet": "discovery"},
    "curator":       {"tiers": ["org"],           "fleet": "discovery"},
    "analyst":       {"tiers": ["org"],           "fleet": "discovery"},
    "interviewer":   {"tiers": ["org"],           "fleet": "discovery"},
    "strategist":    {"tiers": ["org", "skill"],  "fleet": "any"},
    "architect":     {"tiers": ["org", "project"], "fleet": "build"},
    "cartographer":  {"tiers": ["org", "project"], "fleet": "build"},
    "forger-rpa":    {"tiers": ["skill", "project"], "fleet": "build"},
    "forger-coded":  {"tiers": ["skill", "project"], "fleet": "build"},
    "forger-agent":  {"tiers": ["skill", "project"], "fleet": "build"},
    "forger-maestro":{"tiers": ["skill", "project"], "fleet": "build"},
    "reviewer":      {"tiers": ["org", "project"], "fleet": "build"},
    "tester":        {"tiers": ["org", "project"], "fleet": "build"},
    "sentry":        {"tiers": [],                "fleet": "operate"},
    "diagnostician": {"tiers": ["skill", "org"],  "fleet": "operate"},
    "surgeon":       {"tiers": ["project", "skill"], "fleet": "operate"},
    "auditor":       {"tiers": ["org", "project"], "fleet": "operate"},
    "concierge":     {"tiers": [],                "fleet": "operate"},
    "conductor":     {"tiers": ["org"],           "fleet": "any"},
}


def recall(
    *,
    query: str | None = None,
    agent: str | None = None,
    candidate: str | None = None,
    tier: str | None = None,
    fleet: str | None = None,
    since: timedelta | None = None,
    limit: int = 10,
    home: Path | None = None,
) -> list[dict]:
    """Return ranked memory slices.

    Args:
        query: free-text search; if None and `candidate` given, defaults to project recall
        agent: when provided, applies AGENT_DEFAULTS for tier + fleet scoping
        candidate: project id; restricts project-tier reads
        tier: "project" | "org" | "skill" | "any" | None (use agent default)
        fleet: restrict org-tier reads to a fleet's scope
        since: time window
        limit: max items to return
    """
    store = MemoryStore(home)
    defaults = AGENT_DEFAULTS.get(agent or "", {})
    tiers = (
        [tier] if tier and tier != "any"
        else (defaults.get("tiers") or ["project", "org", "skill"])
    )
    fleet = fleet or defaults.get("fleet")
    cutoff_ts = (datetime.now(UTC) - since).isoformat() if since else None

    slices: list[MemorySlice] = []

    if "project" in tiers and candidate:
        project_dir = store.project_dir(candidate)
        for p in project_dir.rglob("*.md"):
            text = p.read_text(encoding="utf-8")
            if query and query.lower() not in text.lower() and not _term_match(text, query):
                continue
            slices.append(MemorySlice(
                path=str(p),
                snippet=text[:400],
                score=1.0,
                tier="project",
            ))

    if "org" in tiers and query:
        slices.extend(store.search_org(query, limit=limit, fleet=fleet if fleet != "any" else None))

    if "skill" in tiers:
        for learning in store.iter_learnings(since=since):
            if cutoff_ts and learning.ts < cutoff_ts:
                continue
            if query and not _term_match(learning.summary, query):
                continue
            slices.append(MemorySlice(
                path=f".aurora/learnings/{learning.ts.split('T')[0]}.jsonl#{learning.agent}",
                snippet=learning.summary,
                score=0.7,
                ts=learning.ts,
                tier="skill",
            ))
        # Plus relevant fingerprint clusters
        for c in list_clusters(limit=limit):
            if query and query.lower() not in (c.get("kind", "") + c.get("refinement", "") + c.get("locality", "")).lower():
                continue
            slices.append(MemorySlice(
                path=f"<fingerprint:{c['cluster_id']}>",
                snippet=f"{c['kind']}/{c.get('refinement', '')} @ {c.get('locality', '')} — {c['occ']} occurrences",
                score=0.6,
                tier="skill",
            ))

    # Rank: 0.5 recency + 0.3 relevance + 0.15 scope + 0.05 resolved bonus
    ranked = sorted(slices, key=lambda s: _rank(s, query, fleet), reverse=True)[:limit]
    return [asdict(s) for s in ranked]


def _term_match(text: str, query: str | None) -> bool:
    if not query:
        return True
    terms = [t.lower() for t in query.split() if len(t) >= 3]
    if not terms:
        return True
    low = text.lower()
    return all(t in low for t in terms[:3])  # at least the first 3 substantial terms


def _rank(s: MemorySlice, query: str | None, fleet: str | None) -> float:
    recency = 1.0
    if s.ts:
        try:
            age_days = (datetime.now(UTC) - datetime.fromisoformat(s.ts.replace("Z", "+00:00"))).days
            recency = math.exp(-age_days / 30)  # 30-day half-life
        except ValueError:
            pass
    relevance = s.score
    scope = 1.0  # placeholder — would inspect fleet tag
    resolved_bonus = 0.0
    return 0.5 * recency + 0.3 * relevance + 0.15 * scope + 0.05 * resolved_bonus
