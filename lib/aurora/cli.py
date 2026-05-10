"""`aurora` CLI entry point.

Subcommands:
    aurora start [--skip-daemons] [--policy PATH]
    aurora status [--once] [--filter fleet=NAME]
    aurora policy validate [--strict] [--live]
    aurora policy dry-run [--since DURATION]
    aurora policy reload
    aurora recall <query> [--tier T] [--fleet F] [--limit N] [--since D]
    aurora feedback [--include LIST] [--note TEXT]
    aurora restart
    aurora compost [--since N] [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, timedelta
from pathlib import Path

from aurora import __version__
from aurora.auth import ensure_fresh_token
from aurora.policy import PolicyError, find_repo_root, load_policy
from aurora.policy import dry_run as policy_dry_run
from aurora.recall import recall as recall_fn

logger = logging.getLogger(__name__)


def _parse_duration(s: str) -> timedelta:
    """'7d' / '24h' / '30m' -> timedelta."""
    if not s:
        raise ValueError("empty duration")
    n, unit = int(s[:-1]), s[-1].lower()
    return {"d": timedelta(days=n), "h": timedelta(hours=n), "m": timedelta(minutes=n)}[unit]


# ---------- start ----------

def cmd_start(args: argparse.Namespace) -> int:
    print("[aurora] loading policy…", flush=True)
    try:
        _policy, warnings = load_policy(path=Path(args.policy) if args.policy else None)
    except PolicyError as e:
        print(f"[aurora] policy invalid: {e}", file=sys.stderr)
        return 1
    for w in warnings:
        print(f"[aurora] warning: {w}", file=sys.stderr)
    print(f"[aurora] policy: valid ({len(warnings)} warning(s))")

    print("[aurora] minting UiPath token…", flush=True)
    repo_root = find_repo_root()
    token = ensure_fresh_token(write_dotenv_path=repo_root / ".env")
    print(f"[aurora] uipath token: minted, expires_at={token.expires_at}, scopes={len(token.scope.split())}")

    if args.skip_daemons:
        print("[aurora] --skip-daemons: not starting Operate fleet")
        print("[aurora] conductor: ready (in-session mode)")
        return 0

    # Spawn the conductor daemon in-process.
    print("[aurora] starting conductor daemon…", flush=True)
    from aurora.conductor import main_async as conductor_main
    return asyncio.run(conductor_main())


# ---------- status ----------

def cmd_status(args: argparse.Namespace) -> int:
    if args.once or args.json:
        # Placeholder structured snapshot
        snapshot = {
            "agents": {"discovery": 5, "build": 8, "operate": 5, "meta": 1},
            "backlog": {"pending-analyst": 0, "ready-for-architect": 0, "forging": 0, "operating": 0},
            "gates_open": [],
            "events_recent": [],
            "budget_today_usd": {"spent": 0.0, "cap": 0.0},
        }
        if args.json:
            print(json.dumps(snapshot, indent=2))
        else:
            print(f"AURORA — {snapshot['agents']}")
        return 0

    # Full TUI (Textual) — only when stdout is a real TTY. Falls through to the
    # JSON snapshot otherwise so piped/scripted invocations stay deterministic.
    if not sys.stdout.isatty():
        return cmd_status(argparse.Namespace(**{**vars(args), "json": True, "once": True}))

    from aurora.tui.app import AuroraStatusApp
    AuroraStatusApp().run()
    return 0


# ---------- policy ----------

def cmd_policy(args: argparse.Namespace) -> int:
    if args.policy_cmd == "validate":
        try:
            _, warnings = load_policy(strict=args.strict)
        except PolicyError as e:
            print(f"[aurora-policy] {e}", file=sys.stderr)
            return 1
        for w in warnings:
            print(f"[aurora-policy] warning: {w}", file=sys.stderr)
        live_failed = False
        if args.live:
            from aurora.policy_live import run_live_probes
            print("[aurora-policy] running live probes (orchestrator, github, action-catalog)…")
            probes = run_live_probes()
            for f in probes.failures:
                print(f"[aurora-policy] live: {f}", file=sys.stderr)
            if not probes.all_ok:
                live_failed = True
                print(
                    f"[aurora-policy] live probes: {sum([probes.orchestrator_ok, probes.github_ok, probes.action_catalog_ok])}/3 ok",
                    file=sys.stderr,
                )
            else:
                print("[aurora-policy] live probes: 3/3 ok")
        print(f"[aurora-policy] valid ({len(warnings)} warning(s))")
        if live_failed:
            return 3
        return 0 if not (args.strict and warnings) else 2

    if args.policy_cmd == "dry-run":
        policy, _ = load_policy()
        forecast = policy_dry_run(policy)
        print(json.dumps(forecast, indent=2))
        return 0

    if args.policy_cmd == "reload":
        # In v2 this signals the running daemon. For now, just re-validate.
        _, warnings = load_policy()
        print(f"[aurora-policy] reloaded ({len(warnings)} warning(s))")
        return 0

    print("usage: aurora policy {validate,dry-run,reload}", file=sys.stderr)
    return 2


# ---------- recall ----------

def cmd_recall(args: argparse.Namespace) -> int:
    since = _parse_duration(args.since) if args.since else None
    results = recall_fn(
        query=args.query,
        tier=args.tier,
        fleet=args.fleet,
        candidate=args.candidate,
        limit=args.limit,
        since=since,
    )
    print(json.dumps(results, indent=2, default=str))
    return 0


# ---------- feedback ----------

def cmd_feedback(args: argparse.Namespace) -> int:
    print("[aurora-feedback] feedback bundle not yet implemented in v1")
    if args.note:
        print(f"  note: {args.note}")
    return 0


# ---------- restart ----------

def cmd_restart(_: argparse.Namespace) -> int:
    print("[aurora] restart not yet implemented; stop the systemd unit and `aurora start`")
    return 0


# ---------- compost ----------

def cmd_compost(args: argparse.Namespace) -> int:
    from datetime import datetime

    from aurora.compost import propose_skill_pr

    home = Path(os.environ.get("AURORA_HOME", str(Path.home() / ".aurora")))
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    learnings_path = home / "learnings" / f"{date}.jsonl"

    results = propose_skill_pr(learnings_path, dry_run=bool(args.dry_run))
    print(json.dumps([r.model_dump() for r in results], indent=2, default=str))
    return 0


# ---------- main ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aurora", description="AURORA — UiPath coding-agent swarm")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="boot the swarm")
    s.add_argument("--skip-daemons", action="store_true")
    s.add_argument("--policy", default=None)
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("status", help="dashboard / snapshot")
    s.add_argument("--once", action="store_true")
    s.add_argument("--json", action="store_true")
    s.add_argument("--filter", default=None)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("policy", help="validate / dry-run / reload policy.yaml")
    sp = s.add_subparsers(dest="policy_cmd", required=True)
    pv = sp.add_parser("validate")
    pv.add_argument("--strict", action="store_true")
    pv.add_argument("--live", action="store_true")
    sp.add_parser("dry-run")
    sp.add_parser("reload")
    s.set_defaults(func=cmd_policy)

    s = sub.add_parser("recall", help="search swarm memory")
    s.add_argument("query", nargs="+")
    s.add_argument("--tier", choices=["project", "org", "skill", "any"], default=None)
    s.add_argument("--fleet", choices=["discovery", "build", "operate"], default=None)
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--since", default=None)
    s.add_argument("--candidate", default=None)
    s.set_defaults(func=cmd_recall)

    s = sub.add_parser("feedback", help="send a session report to UiPath")
    s.add_argument("--include", default="all")
    s.add_argument("--note", default=None)
    s.set_defaults(func=cmd_feedback)

    s = sub.add_parser("restart", help="recycle the daemon")
    s.set_defaults(func=cmd_restart)

    s = sub.add_parser("compost", help="run the nightly compost step")
    s.add_argument("--since", default="1d")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_compost)

    return p


def main() -> int:
    logging.basicConfig(level=os.environ.get("AURORA_LOG_LEVEL", "INFO"))
    parser = build_parser()
    args = parser.parse_args()

    # Normalize positional `recall` arg into a string
    if getattr(args, "cmd", None) == "recall":
        args.query = " ".join(args.query)

    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
