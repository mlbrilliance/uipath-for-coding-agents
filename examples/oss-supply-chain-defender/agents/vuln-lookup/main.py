"""Entry point for the AuroraVulnLookup Coded Agent.

Two functions:
    main(input)   — bulk lookup over a lockfiles batch (called from Maestro VulnLookup)
    triage(input) — single-finding deep triage with remediation proposal (called from
                    Maestro Triage in the Critical sub-process)

Both run a LangGraph state machine defined in graph.py. Tools (NVD, OSV, Advisory)
live in tools/. Prompts live in prompts/.
"""
from __future__ import annotations

import logging
from typing import Any

import structlog
from uipath import UiPath  # type: ignore[import-not-found]

from graph import build_graph
from models import Finding, LockfileBatch, TriageResult, TriageInput

logger = structlog.get_logger(__name__)


# ---------- Maestro entry: VulnLookup task ----------

def main(input: dict[str, Any]) -> dict[str, Any]:
    """Bulk lookup over multiple lockfiles."""
    batch = LockfileBatch.model_validate(input)
    logger.info("vuln-lookup.start", repos=len(batch.lockfiles))

    graph = build_graph()
    state = {
        "lockfiles": batch.lockfiles,
        "findings": [],
        "max_cvss": 0.0,
        "has_known_exploit": False,
        "shallowest_depth": 9999,
    }
    final = graph.invoke(state)

    findings = [Finding.model_validate(f) for f in final["findings"]]
    response = {
        "findings": [f.model_dump() for f in findings],
        "max_cvss": final["max_cvss"],
        "has_known_exploit": final["has_known_exploit"],
        "shallowest_depth": final["shallowest_depth"],
        "total_count": len(findings),
    }

    logger.info(
        "vuln-lookup.complete",
        total=response["total_count"],
        max_cvss=response["max_cvss"],
        exploit=response["has_known_exploit"],
    )
    return response


# ---------- Maestro entry: Triage task (Critical sub-process) ----------

def triage(input: dict[str, Any]) -> dict[str, Any]:
    """Deep triage of one or more findings; proposes a concrete remediation."""
    payload = TriageInput.model_validate(input)

    sdk = UiPath()  # subscription-OAuth via ~/.claude/credentials.json
    # Surface findings to the LLM via the same graph but with a 'triage' entry mode
    graph = build_graph(mode="triage")
    state = {
        "findings": [f.model_dump() for f in payload.findings],
        "remediation_diff": None,
        "rationale": None,
    }
    final = graph.invoke(state)

    result = TriageResult(
        triage_summary=final["rationale"],
        proposed_diff=final["remediation_diff"],
    )
    logger.info("vuln-lookup.triage", findings=len(payload.findings))
    return result.model_dump()


if __name__ == "__main__":
    # Local debug: read input.json from the cwd and print output.
    import json
    import sys
    from pathlib import Path

    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("input.json")
    payload = json.loads(in_path.read_text())
    print(json.dumps(main(payload), indent=2))
