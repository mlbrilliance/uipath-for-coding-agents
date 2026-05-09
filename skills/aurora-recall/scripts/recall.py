#!/usr/bin/env python3
"""Subprocess wrapper for memory retrieval — invoked by hooks and slash commands.

Thin CLI on top of `aurora.recall.recall(...)`. Outputs JSON suitable for
embedding into a Claude Code `additionalContext` hook payload.

Exit codes:
  0 — success (may return empty list)
  1 — error (missing dependencies, malformed args)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path


def _add_lib_to_path() -> None:
    # Allow this script to import aurora.* even when the package isn't installed.
    here = Path(__file__).resolve()
    lib = here.parents[3] / "lib"  # uipath-for-coding-agents/lib/
    if lib.exists() and str(lib) not in sys.path:
        sys.path.insert(0, str(lib))


def _parse_duration(s: str | None) -> timedelta | None:
    if not s:
        return None
    n, unit = int(s[:-1]), s[-1].lower()
    return {"d": timedelta(days=n), "h": timedelta(hours=n), "m": timedelta(minutes=n)}[unit]


def main() -> int:
    p = argparse.ArgumentParser(description="AURORA scoped memory retrieval")
    p.add_argument("--agent", default=None, help="calling agent name (uses defaults if set)")
    p.add_argument("--query", default=None)
    p.add_argument("--candidate", default=None)
    p.add_argument("--tier", choices=["project", "org", "skill", "any"], default=None)
    p.add_argument("--fleet", choices=["discovery", "build", "operate"], default=None)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--since", default=None, help="duration like 7d, 24h, 30m")
    p.add_argument("--format", choices=["full", "minimal"], default="full")
    args = p.parse_args()

    _add_lib_to_path()
    try:
        from aurora.recall import recall  # noqa: WPS433
    except ImportError as e:
        # Hook expects empty context on failure — exit 0 with empty result
        sys.stderr.write(f"[aurora-recall] aurora package not importable: {e}\n")
        print("{}")
        return 0

    try:
        results = recall(
            query=args.query,
            agent=args.agent,
            candidate=args.candidate,
            tier=args.tier,
            fleet=args.fleet,
            limit=args.limit,
            since=_parse_duration(args.since),
        )
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[aurora-recall] error: {e}\n")
        print("{}")
        return 0

    if args.format == "minimal":
        # Compact form for the pre-tool hook — paths + 1-line snippets only
        compact = [
            {"path": r.get("path"), "snippet": r.get("snippet", "")[:200]}
            for r in results
        ]
        print(json.dumps(compact, separators=(",", ":")))
    else:
        print(json.dumps(results, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
