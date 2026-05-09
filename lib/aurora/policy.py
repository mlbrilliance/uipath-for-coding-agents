"""policy.yaml loader, validator, and dry-run.

Wraps `skills/aurora-policy/scripts/validate_policy.py` with an in-process
loader that returns a typed `AuroraPolicy` for use by Conductor.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

logger = logging.getLogger(__name__)

ENV_REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


@dataclass(frozen=True)
class AuroraPolicy:
    """Typed view over policy.yaml after env expansion + schema validation."""
    version: int
    identity: dict
    uipath_scopes: list[str]
    discovery: dict
    build: dict
    deploy: dict
    operate: dict
    gates: list[dict]
    memory: dict
    routing: dict
    budget: dict
    raw: dict = field(repr=False, default_factory=dict)

    # Convenience accessors

    @property
    def folder(self) -> str:
        return self.identity["uipath_folder"]

    @property
    def action_catalog(self) -> str:
        return self.identity["action_catalog"]

    @property
    def github_org(self) -> str:
        return self.identity["github_org"]

    @property
    def scope_string(self) -> str:
        return " ".join(self.uipath_scopes)

    def model_for_agent(self, agent: str) -> str:
        """Resolve the agent's model binding through the routing tier."""
        tier = self.routing["bindings"].get(agent, "mid_stakes")
        return self.routing["defaults"][tier]

    def gate(self, name: str) -> dict:
        for g in self.gates:
            if g.get("name") == name:
                return g
        raise KeyError(f"no gate named {name!r}")


class PolicyError(RuntimeError):
    """Raised on schema, env, or sanity-check failure."""


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from start (or cwd) looking for policy.yaml."""
    cur = (start or Path.cwd()).resolve()
    for d in [cur, *cur.parents][:6]:
        if (d / "policy.yaml").exists():
            return d
    raise FileNotFoundError("policy.yaml not found in cwd or up to 5 parents")


def expand_env(obj: Any) -> Any:
    """Recursively expand ${VAR} references against os.environ."""
    if isinstance(obj, str):
        def repl(m: re.Match[str]) -> str:
            var = m.group(1)
            val = os.environ.get(var)
            if val is None:
                raise PolicyError(f"unresolved env var: {var}")
            return val
        return ENV_REF.sub(repl, obj)
    if isinstance(obj, list):
        return [expand_env(x) for x in obj]
    if isinstance(obj, dict):
        return {k: expand_env(v) for k, v in obj.items()}
    return obj


def validate_policy(
    policy: dict,
    *,
    schema_path: Path | None = None,
    strict: bool = False,
) -> list[str]:
    """Validate against schema. Returns warnings; raises PolicyError on errors."""
    schema_path = schema_path or (find_repo_root() / "policy.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(policy), key=lambda e: list(e.path))
    if errors:
        msgs = ["/".join(str(x) for x in e.path) + ": " + e.message for e in errors]
        raise PolicyError("schema errors:\n  - " + "\n  - ".join(msgs))

    warnings = _soft_warnings(policy)
    if warnings and strict:
        raise PolicyError("strict mode: warnings present:\n  - " + "\n  - ".join(warnings))
    return warnings


def _soft_warnings(policy: dict) -> list[str]:
    out: list[str] = []
    if policy.get("build", {}).get("test_coverage_floor", 1.0) < 0.7:
        out.append("build.test_coverage_floor < 0.7 — too lenient")
    if policy.get("deploy", {}).get("prod", {}).get("auto", False):
        out.append("deploy.prod.auto == true — production publishes auto-trigger; uncommon")
    gate_names = {g.get("name") for g in policy.get("gates", [])}
    if "emergency_patch" not in gate_names:
        out.append("no emergency_patch gate defined")
    surgeon = policy.get("operate", {}).get("surgeon", {})
    try:
        if int(surgeon.get("max_auto_fixes_per_day", 0)) > 20:
            out.append(f"surgeon.max_auto_fixes_per_day = {surgeon['max_auto_fixes_per_day']} — high autonomy")
    except (TypeError, ValueError):
        pass
    if not policy.get("discovery", {}).get("sources"):
        out.append("discovery.sources is empty — Discovery fleet has nothing to listen to")
    try:
        if float(policy.get("budget", {}).get("daily_usd", 0)) < 5:
            out.append(f"budget.daily_usd = {policy['budget']['daily_usd']} — likely too low")
    except (TypeError, ValueError):
        pass
    for g in policy.get("gates", []):
        if g.get("name") == "skill_compost_pr" and g.get("auto_merge"):
            out.append("skill_compost_pr.auto_merge=true is forbidden by policy — overriding")
    return out


def load_policy(
    *,
    path: Path | None = None,
    strict: bool = False,
) -> tuple[AuroraPolicy, list[str]]:
    """Load + expand + validate. Returns (policy, warnings)."""
    path = path or (find_repo_root() / "policy.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    expanded = expand_env(raw)
    warnings = validate_policy(expanded, strict=strict)

    return (
        AuroraPolicy(
            version=expanded["version"],
            identity=expanded["identity"],
            uipath_scopes=expanded["uipath_scopes"],
            discovery=expanded["discovery"],
            build=expanded["build"],
            deploy=expanded["deploy"],
            operate=expanded["operate"],
            gates=expanded["gates"],
            memory=expanded["memory"],
            routing=expanded["routing"],
            budget=expanded["budget"],
            raw=expanded,
        ),
        warnings,
    )


def dry_run(policy: AuroraPolicy, *, since_hours: int = 24) -> dict:
    """Simulate Conductor's next N hours given the current backlog and Operate state.

    This is a SHAPE check, not an execution. Returns a structured forecast that
    `aurora policy dry-run` renders for humans.
    """
    # Stub for v1 — populate from real backlog state in v2
    return {
        "horizon_hours": since_hours,
        "would_dispatch": [
            {"agent": "analyst", "count": 0, "estimated_minutes": 0},
            {"agent": "architect", "count": 0, "estimated_minutes": 0},
        ],
        "gates_that_would_fire": [],
        "token_budget_projection_usd": 0.0,
        "operate_fleet": {
            "sentry_polls_per_hour": 3600 // max(1, int(policy.operate["sentry"]["poll_interval_seconds"])),
        },
        "warnings": [],
    }
