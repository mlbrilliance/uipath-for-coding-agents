#!/usr/bin/env python3
"""Validate AURORA policy.yaml against policy.schema.json.

Exit codes:
  0 — valid (warnings only)
  1 — invalid (schema error or unresolved env var)
  2 — invalid in strict mode (warnings present)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


ENV_REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def find_root() -> Path:
    """Find repo root by walking up looking for policy.yaml."""
    cwd = Path.cwd().resolve()
    for d in [cwd, *cwd.parents][:6]:
        if (d / "policy.yaml").exists():
            return d
    raise FileNotFoundError("policy.yaml not found in cwd or up to 5 parents")


def expand_env(obj):
    """Recursively expand ${VAR} references against os.environ. Raise on unresolved."""
    if isinstance(obj, str):
        def repl(m):
            var = m.group(1)
            val = os.environ.get(var)
            if val is None:
                raise ValueError(f"unresolved env var: {var}")
            return val
        return ENV_REF.sub(repl, obj)
    if isinstance(obj, list):
        return [expand_env(x) for x in obj]
    if isinstance(obj, dict):
        return {k: expand_env(v) for k, v in obj.items()}
    return obj


def soft_warnings(policy: dict, strict: bool) -> list[str]:
    warns: list[str] = []
    build = policy.get("build", {})
    if build.get("test_coverage_floor", 1.0) < 0.7:
        warns.append("build.test_coverage_floor < 0.7 — too lenient")

    deploy_prod = policy.get("deploy", {}).get("prod", {})
    if deploy_prod.get("auto", False):
        warns.append("deploy.prod.auto == true — production publishes auto-trigger; uncommon")

    gates = policy.get("gates", [])
    gate_names = {g.get("name") for g in gates}
    if "emergency_patch" not in gate_names:
        warns.append("no emergency_patch gate defined")

    operate = policy.get("operate", {}).get("surgeon", {})
    max_fix = operate.get("max_auto_fixes_per_day")
    try:
        if isinstance(max_fix, str):
            max_fix = int(os.environ.get(max_fix.strip("${}"), 0))
        if max_fix and int(max_fix) > 20:
            warns.append(f"surgeon.max_auto_fixes_per_day = {max_fix} — high autonomy")
    except Exception:
        pass

    if not policy.get("discovery", {}).get("sources"):
        warns.append("discovery.sources is empty — Discovery fleet has nothing to listen to")

    budget = policy.get("budget", {}).get("daily_usd")
    try:
        if isinstance(budget, str):
            budget = float(os.environ.get(budget.strip("${}"), 0))
        if budget and float(budget) < 5:
            warns.append(f"budget.daily_usd = {budget} — likely too low; expect frequent pauses")
    except Exception:
        pass

    for g in gates:
        if g.get("name") == "skill_compost_pr" and g.get("auto_merge"):
            warns.append("skill_compost_pr.auto_merge=true is forbidden by policy — overriding")

    return warns


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true", help="warnings exit non-zero")
    p.add_argument("--live", action="store_true", help="probe Orchestrator + GitHub for sanity (slow)")
    p.add_argument("--policy", default=None, help="path to policy.yaml (default: auto-find)")
    p.add_argument("--schema", default=None, help="path to policy.schema.json (default: auto-find)")
    args = p.parse_args()

    root = find_root()
    policy_path = Path(args.policy) if args.policy else root / "policy.yaml"
    schema_path = Path(args.schema) if args.schema else root / "policy.schema.json"

    if not policy_path.exists():
        print(f"[aurora-policy] missing {policy_path}", file=sys.stderr)
        return 1
    if not schema_path.exists():
        print(f"[aurora-policy] missing {schema_path}", file=sys.stderr)
        return 1

    raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    # Expand env vars before schema validation so type checks ("number" vs "string") work
    try:
        expanded = expand_env(raw)
    except ValueError as e:
        print(f"[aurora-policy] {e}", file=sys.stderr)
        return 1

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(expanded), key=lambda e: e.path)
    if errors:
        for e in errors:
            loc = "/".join(str(x) for x in e.path) or "<root>"
            print(f"[aurora-policy] error at {loc}: {e.message}", file=sys.stderr)
        return 1

    warns = soft_warnings(expanded, args.strict)
    for w in warns:
        print(f"[aurora-policy] warning: {w}", file=sys.stderr)

    if args.live:
        # Live checks could go here — Orchestrator folder existence, catalog existence, GitHub org reachability
        print("[aurora-policy] --live not yet wired (TODO: invoke uipath_client + GitHub probe)", file=sys.stderr)

    if warns and args.strict:
        return 2

    print(f"[aurora-policy] {policy_path.name}: valid ({len(warns)} warning(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
