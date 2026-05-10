"""LangGraph state machine for vulnerability lookup and triage.

Nodes:
    parse_lockfiles       — normalize {ecosystem, name, version} tuples
    nvd_lookup            — query NVD CVE feed per dep
    osv_lookup            — query OSV.dev per dep
    advisory_lookup       — query GitHub Advisory DB per dep
    synthesize            — merge results, dedupe, score
    propose_remediation   — (triage mode only) draft a version-bump diff

The graph is deliberately straightforward — three parallel external queries
that fan in to a synthesis step. LangGraph's parallel-then-merge pattern
makes this clean.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, TypedDict

import structlog
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, StateGraph
from models import Finding, LockfileEntry
from tools import github_advisory, nvd, osv

logger = structlog.get_logger(__name__)


class State(TypedDict, total=False):
    lockfiles: list[dict]      # raw input, may include nested deps
    deps: list[LockfileEntry]  # normalized
    findings: list[dict]
    max_cvss: float
    has_known_exploit: bool
    shallowest_depth: int
    # Triage-mode fields:
    rationale: str | None
    remediation_diff: dict | None


def parse_lockfiles_node(state: State) -> State:
    """Normalize the input lockfiles into a flat list of {ecosystem, name, version, depth}."""
    deps: list[LockfileEntry] = []
    for lf in state.get("lockfiles", []):
        ecosystem = lf.get("ecosystem", "")
        for d in lf.get("deps", []):
            deps.append(LockfileEntry(
                ecosystem=ecosystem,
                name=d["name"],
                version=d["version"],
                depth=d.get("depth", 1),
            ))
    state["deps"] = deps
    return state


def lookup_node(state: State) -> State:
    """Run NVD + OSV + Advisory queries in parallel, merge into findings."""
    deps = state["deps"]
    if not deps:
        state["findings"] = []
        return state

    async def gather() -> list[Finding]:
        tasks = []
        for d in deps:
            tasks.append(nvd.lookup(d))
            tasks.append(osv.lookup(d))
            tasks.append(github_advisory.lookup(d))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: list[Finding] = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("lookup_failed", error=str(r))
                continue
            if r:
                merged.extend(r)
        return _dedupe_findings(merged)

    findings = asyncio.run(gather())
    state["findings"] = [f.model_dump() for f in findings]
    return state


def synthesize_node(state: State) -> State:
    findings = state.get("findings", [])
    state["max_cvss"] = max((f.get("cvss", 0.0) for f in findings), default=0.0)
    state["has_known_exploit"] = any(f.get("exploit_in_wild") for f in findings)
    state["shallowest_depth"] = min((f.get("depth", 9999) for f in findings), default=9999)
    return state


def propose_remediation_node(state: State) -> State:
    """LLM-backed step: read findings, propose a concrete version-bump diff + rationale."""
    findings = state.get("findings", [])
    if not findings:
        state["rationale"] = "no findings; nothing to remediate"
        state["remediation_diff"] = None
        return state

    prompt = (Path(__file__).parent / "prompts" / "triage.md").read_text(encoding="utf-8")
    llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
    response = llm.invoke([
        {"role": "system", "content": prompt},
        {"role": "user", "content": _format_findings_for_llm(findings)},
    ])
    text = response.content if isinstance(response.content, str) else str(response.content)

    # The prompt instructs the LLM to emit a JSON envelope; parse it.
    import json
    import re
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        state["rationale"] = text
        state["remediation_diff"] = None
        return state
    try:
        envelope = json.loads(match.group(0))
        state["rationale"] = envelope.get("rationale", text)
        state["remediation_diff"] = envelope.get("diff")
    except json.JSONDecodeError:
        state["rationale"] = text
        state["remediation_diff"] = None
    return state


def build_graph(mode: str = "lookup") -> Any:
    """Compile the state machine.

    mode='lookup'  : parse -> lookup -> synthesize -> END
    mode='triage'  : parse -> lookup -> synthesize -> propose_remediation -> END
    """
    g: StateGraph = StateGraph(State)
    g.add_node("parse_lockfiles", parse_lockfiles_node)
    g.add_node("lookup", lookup_node)
    g.add_node("synthesize", synthesize_node)

    g.set_entry_point("parse_lockfiles")
    g.add_edge("parse_lockfiles", "lookup")
    g.add_edge("lookup", "synthesize")

    if mode == "triage":
        g.add_node("propose_remediation", propose_remediation_node)
        g.add_edge("synthesize", "propose_remediation")
        g.add_edge("propose_remediation", END)
    else:
        g.add_edge("synthesize", END)

    return g.compile()


# ---------- helpers ----------

def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    """Same package + same CVE id from different sources -> keep highest CVSS."""
    out: dict[tuple[str, str, str], Finding] = {}
    for f in findings:
        key = (f.ecosystem, f.package, f.advisory_id)
        existing = out.get(key)
        if existing is None or (f.cvss or 0) > (existing.cvss or 0):
            out[key] = f
    return list(out.values())


def _format_findings_for_llm(findings: list[dict]) -> str:
    lines = ["Findings (one per line, JSONL-ish):"]
    for f in findings:
        lines.append(
            f"- {f['ecosystem']}/{f['package']}@{f['version']} "
            f"({f['advisory_id']}, cvss={f.get('cvss')}, exploit_in_wild={f.get('exploit_in_wild')})"
        )
    return "\n".join(lines)
