"""Failure-event fingerprinting and clustering.

Runtime-side counterpart to `skills/aurora-fingerprint/scripts/cluster.py`.
Both modules share the same SQLite schema and taxonomy; the script form is
for shellouts (post-tool hook), the module form is for in-process use by
Diagnostician and Surgeon.

Top-level kinds (canonical):
    selector-broken, auth-failed, external-api-drift, null-arg, timing,
    data-quality, network, license

Anything else gets `kind: novel-fault` and is escalated.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

CANONICAL_KINDS = {
    "selector-broken", "auth-failed", "external-api-drift",
    "null-arg", "timing", "data-quality", "network", "license",
}

TOKEN_PATTERNS = [
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"\bhttps?://[^\s'\"]+"), "<url>"),
    (re.compile(r"[a-zA-Z]:\\[^\s'\"]+|/[^\s'\"]*/[^\s'\"]+"), "<path>"),
    (re.compile(r"\b\d{6,}\b"), "<id>"),
    (re.compile(r"\b\d+\.\d+(\.\d+)?(\.\d+)?\b"), "<version>"),
    (re.compile(r"<wnd[^>]*>|<html[^>]*>|<webctrl[^>]*>|<aa[^>]*>|<uia[^>]*>"), "<selector>"),
]


@dataclass(frozen=True)
class ClusterResult:
    fingerprint_id: str
    cluster_id: str
    kind: str
    refinement: str
    locality: str
    size: int
    novel: bool
    confidence: float
    prior_resolution: dict | None


def db_path() -> Path:
    home = Path(os.environ.get("AURORA_HOME", "/opt/aurora"))
    home.mkdir(parents=True, exist_ok=True)
    return home / "fingerprints.db"


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(db_path())
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS fingerprints (
            id TEXT PRIMARY KEY,
            cluster_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            refinement TEXT,
            locality TEXT,
            exception_type TEXT,
            message_skeleton TEXT,
            project_id TEXT,
            first_seen TEXT,
            last_seen TEXT,
            occurrences INTEGER DEFAULT 1,
            resolution_pr TEXT,
            resolution_summary TEXT
        );
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_cluster ON fingerprints(cluster_id);")
    c.execute("CREATE INDEX IF NOT EXISTS idx_kind ON fingerprints(kind);")
    c.commit()
    return c


def message_skeleton(msg: str) -> str:
    out = msg or ""
    for pat, repl in TOKEN_PATTERNS:
        out = pat.sub(repl, out)
    return out[:500]


def derive_kind(event: dict) -> str:
    et = (event.get("details", {}).get("exception_type") or "").lower()
    msg = (event.get("details", {}).get("message") or "").lower()
    if "selectornotfound" in et or "selector" in msg:
        return "selector-broken"
    if any(s in msg for s in ("401", "403", "unauthorized", "forbidden")):
        return "auth-failed"
    if "timeout" in et or "timeout" in msg:
        return "timing"
    if "nullreference" in et or "argumentnull" in et:
        return "null-arg"
    if "license" in msg:
        return "license"
    if any(s in msg for s in ("dns", "connection refused", "ssl", "tls")):
        return "network"
    return "novel-fault"


def derive_refinement(kind: str, exception_type: str, msg: str) -> str:
    m = (msg or "").lower()
    if kind == "selector-broken":
        if "aaname" in m:
            return "aaname-mismatch"
        if "wnd" in m:
            return "wnd-mismatch"
        if "html" in m:
            return "html-mismatch"
        if "ambiguous" in m:
            return "ambiguous-multi-match"
        return "generic"
    if kind == "auth-failed":
        if "401" in m:
            return "token-expired"
        if "403" in m:
            return "scope-insufficient"
        return "generic"
    if kind == "timing":
        if "30000" in m or "30s" in m:
            return "timeout-30s"
        return "generic"
    return "generic"


def classify_event(event: dict) -> ClusterResult:
    """Map an event to a fingerprint, update SQLite, return cluster info."""
    details = event.get("details", {})
    kind = event.get("kind") or "novel-fault"
    if kind not in CANONICAL_KINDS and kind != "novel-fault":
        kind = derive_kind(event)

    exception_type = details.get("exception_type", "")
    msg = details.get("message", "")
    locality = details.get("step") or details.get("workflow") or ""
    refinement = derive_refinement(kind, exception_type, msg)
    skeleton = message_skeleton(msg)

    raw_fid = f"{kind}|{refinement}|{locality}|{exception_type}|{skeleton}"
    fid = hashlib.sha256(raw_fid.encode("utf-8")).hexdigest()[:16]
    cid = hashlib.sha256(f"{kind}|{refinement}|{locality}".encode()).hexdigest()[:8]

    db = conn()
    cur = db.cursor()
    ts = event.get("ts")
    cur.execute("SELECT id FROM fingerprints WHERE id=?", (fid,))
    if cur.fetchone():
        cur.execute("UPDATE fingerprints SET last_seen=?, occurrences=occurrences+1 WHERE id=?", (ts, fid))
    else:
        cur.execute(
            "INSERT INTO fingerprints (id, cluster_id, kind, refinement, locality, "
            "exception_type, message_skeleton, project_id, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fid, cid, kind, refinement, locality, exception_type, skeleton,
             event.get("scope", {}).get("process"), ts, ts),
        )
    db.commit()

    cur.execute("SELECT SUM(occurrences) AS n FROM fingerprints WHERE cluster_id=?", (cid,))
    size = cur.fetchone()["n"] or 1

    cur.execute(
        "SELECT resolution_pr, resolution_summary FROM fingerprints "
        "WHERE cluster_id=? AND resolution_pr IS NOT NULL "
        "ORDER BY last_seen DESC LIMIT 1",
        (cid,),
    )
    res = cur.fetchone()
    prior = {"pr": res["resolution_pr"], "summary": res["resolution_summary"]} if (res and res["resolution_pr"]) else None

    confidence = min(0.95, 0.30 + 0.05 * size)
    novel = (size <= 1) or (kind == "novel-fault")

    return ClusterResult(
        fingerprint_id=fid,
        cluster_id=cid,
        kind=kind,
        refinement=refinement,
        locality=locality,
        size=size,
        novel=novel,
        confidence=round(confidence, 2),
        prior_resolution=prior,
    )


def append_resolution(*, cluster_id: str, pr: str, summary: str) -> None:
    db = conn()
    db.execute(
        "UPDATE fingerprints SET resolution_pr=?, resolution_summary=? WHERE cluster_id=?",
        (pr, summary, cluster_id),
    )
    db.commit()


def list_clusters(*, kind: str | None = None, limit: int = 20) -> list[dict]:
    db = conn()
    if kind:
        rows = db.execute(
            "SELECT cluster_id, kind, refinement, locality, SUM(occurrences) AS occ "
            "FROM fingerprints WHERE kind=? GROUP BY cluster_id ORDER BY occ DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT cluster_id, kind, refinement, locality, SUM(occurrences) AS occ "
            "FROM fingerprints GROUP BY cluster_id ORDER BY occ DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
