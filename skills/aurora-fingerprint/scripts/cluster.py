#!/usr/bin/env python3
"""Cluster failure events by structural fingerprint.

Subcommands:
  classify  --event-file <path>           classify an event; emit JSON with cluster info
  append    --resolution                  attach a Surgeon resolution to an existing cluster
  list      [--kind X] [--limit N]        list known clusters (debug)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

CANONICAL_KINDS = {
    "selector-broken", "auth-failed", "external-api-drift",
    "null-arg", "timing", "data-quality", "network", "license",
}


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


# Token patterns to redact in message_skeleton — each replaces with <type>.
TOKEN_PATTERNS = [
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<uuid>"),
    (re.compile(r"\bhttps?://[^\s'\"]+"), "<url>"),
    (re.compile(r"[a-zA-Z]:\\[^\s'\"]+|/[^\s'\"]*/[^\s'\"]+"), "<path>"),
    (re.compile(r"\b\d{6,}\b"), "<id>"),
    (re.compile(r"\b\d+\.\d+(\.\d+)?(\.\d+)?\b"), "<version>"),
    (re.compile(r"<wnd[^>]*>|<html[^>]*>|<webctrl[^>]*>|<aa[^>]*>|<uia[^>]*>"), "<selector>"),
]


def message_skeleton(msg: str) -> str:
    out = msg or ""
    for pat, repl in TOKEN_PATTERNS:
        out = pat.sub(repl, out)
    return out[:500]  # cap


def fingerprint_id(kind: str, refinement: str, locality: str, exception_type: str, skeleton: str) -> str:
    raw = f"{kind}|{refinement}|{locality}|{exception_type}|{skeleton}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def short_cluster_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]


def classify(event: dict) -> dict:
    """Map an event to a fingerprint; create or update the row; return cluster info."""
    details = event.get("details", {})
    kind = event.get("kind") or "novel-fault"
    if kind not in CANONICAL_KINDS and kind != "novel-fault":
        # Caller didn't specify a canonical kind — derive a guess
        kind = derive_kind(event)

    exception_type = details.get("exception_type", "")
    msg = details.get("message", "")
    locality = details.get("step") or details.get("workflow") or ""
    refinement = derive_refinement(kind, exception_type, msg)
    skeleton = message_skeleton(msg)

    fid = fingerprint_id(kind, refinement, locality, exception_type, skeleton)
    cid = short_cluster_id(f"{kind}|{refinement}|{locality}")

    db = conn()
    cur = db.cursor()
    cur.execute("SELECT * FROM fingerprints WHERE id = ?", (fid,))
    existing = cur.fetchone()

    ts = event.get("ts")
    if existing:
        cur.execute(
            "UPDATE fingerprints SET last_seen=?, occurrences=occurrences+1 WHERE id=?",
            (ts, fid),
        )
    else:
        cur.execute(
            "INSERT INTO fingerprints (id, cluster_id, kind, refinement, locality, "
            "exception_type, message_skeleton, project_id, first_seen, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fid, cid, kind, refinement, locality, exception_type, skeleton,
             event.get("scope", {}).get("process"), ts, ts),
        )
    db.commit()

    # Cluster size
    cur.execute("SELECT SUM(occurrences) AS n FROM fingerprints WHERE cluster_id=?", (cid,))
    size = cur.fetchone()["n"] or 1

    # Prior resolutions
    cur.execute(
        "SELECT resolution_pr, resolution_summary FROM fingerprints "
        "WHERE cluster_id=? AND resolution_pr IS NOT NULL "
        "ORDER BY last_seen DESC LIMIT 1",
        (cid,),
    )
    res = cur.fetchone()
    prior = None
    if res and res["resolution_pr"]:
        prior = {"pr": res["resolution_pr"], "summary": res["resolution_summary"]}

    confidence = min(0.95, 0.30 + 0.05 * size)  # crude monotonic; tune later
    novel = (size <= 1) or (kind == "novel-fault")

    return {
        "fingerprint_id": fid,
        "cluster_id": cid,
        "kind": kind,
        "refinement": refinement,
        "locality": locality,
        "size": size,
        "novel": novel,
        "confidence": round(confidence, 2),
        "prior_resolution": prior,
    }


def derive_kind(event: dict) -> str:
    """Best-effort kind inference from exception_type + message."""
    et = (event.get("details", {}).get("exception_type") or "").lower()
    msg = (event.get("details", {}).get("message") or "").lower()
    if "selectornotfound" in et or "selector" in msg:
        return "selector-broken"
    if "401" in msg or "403" in msg or "unauthorized" in msg or "forbidden" in msg:
        return "auth-failed"
    if "timeout" in et or "timeout" in msg:
        return "timing"
    if "nullreference" in et or "argumentnull" in et:
        return "null-arg"
    if "license" in msg:
        return "license"
    if "dns" in msg or "connection refused" in msg or "ssl" in msg:
        return "network"
    return "novel-fault"


def derive_refinement(kind: str, exception_type: str, msg: str) -> str:
    m = msg.lower()
    if kind == "selector-broken":
        if "aaname" in m:
            return "aaname-mismatch"
        if "wnd" in m:
            return "wnd-mismatch"
        if "html" in m:
            return "html-mismatch"
        if "match was found, but ambiguous" in m:
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


def append_resolution(cluster_id: str, pr: str, summary: str) -> None:
    db = conn()
    db.execute(
        "UPDATE fingerprints SET resolution_pr=?, resolution_summary=? WHERE cluster_id=?",
        (pr, summary, cluster_id),
    )
    db.commit()


def list_clusters(kind: str | None, limit: int) -> list[dict]:
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


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("classify")
    pc.add_argument("--event-file", required=True)

    pa = sub.add_parser("append")
    pa.add_argument("--resolution", action="store_true")
    pa.add_argument("--cluster", required=True)
    pa.add_argument("--pr", required=True)
    pa.add_argument("--summary", required=True)

    pl = sub.add_parser("list")
    pl.add_argument("--kind", default=None)
    pl.add_argument("--limit", type=int, default=20)

    args = p.parse_args()

    if args.cmd == "classify":
        event = json.loads(Path(args.event_file).read_text())
        result = classify(event)
        print(json.dumps(result, indent=2))
        return 0
    if args.cmd == "append":
        append_resolution(args.cluster, args.pr, args.summary)
        return 0
    if args.cmd == "list":
        rows = list_clusters(args.kind, args.limit)
        print(json.dumps(rows, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
