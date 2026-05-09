"""OSV.dev lookup — fully anonymous, ecosystem-aware.

Endpoint: POST https://api.osv.dev/v1/query with {package, version}
"""
from __future__ import annotations

import logging
import os

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from models import Finding, LockfileEntry

logger = logging.getLogger(__name__)

OSV_BASE = os.environ.get("OSV_API_BASE", "https://api.osv.dev")


_ECOSYSTEM_MAP = {
    "npm": "npm",
    "pypi": "PyPI",
    "go": "Go",
    "rubygems": "RubyGems",
    "maven": "Maven",
    "cargo": "crates.io",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def lookup(dep: LockfileEntry) -> list[Finding]:
    osv_eco = _ECOSYSTEM_MAP.get(dep.ecosystem, dep.ecosystem)
    body = {
        "package": {"name": dep.name, "ecosystem": osv_eco},
        "version": dep.version,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{OSV_BASE}/v1/query", json=body)
        if r.status_code != 200:
            logger.warning("osv: HTTP %d for %s", r.status_code, dep.name)
            return []
        data = r.json()
    except httpx.HTTPError as e:
        logger.warning("osv: %s", e)
        return []

    findings: list[Finding] = []
    for vuln in data.get("vulns", []):
        vuln_id = vuln.get("id", "")
        summary = vuln.get("summary") or vuln.get("details", "")
        cvss = _extract_cvss(vuln)
        fix = _extract_fix(vuln)
        findings.append(Finding(
            ecosystem=dep.ecosystem,
            package=dep.name,
            version=dep.version,
            depth=dep.depth,
            advisory_id=vuln_id,
            title=summary[:200],
            cvss=cvss,
            exploit_in_wild=False,  # OSV doesn't carry exploit signals directly
            fix_version=fix,
            source="osv",
            url=f"https://osv.dev/vulnerability/{vuln_id}",
        ))
    return findings


def _extract_cvss(vuln: dict) -> float | None:
    for sev in vuln.get("severity", []) or []:
        score = sev.get("score") or ""
        # CVSS:3.1/AV:N/...  — find the AV number
        # The simplest path is to look in `database_specific` if present.
        if score and isinstance(score, (int, float)):
            return float(score)
    db = vuln.get("database_specific", {}) or {}
    s = db.get("severity")
    if isinstance(s, (int, float)):
        return float(s)
    if isinstance(s, str):
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _extract_fix(vuln: dict) -> str | None:
    for affected in vuln.get("affected", []) or []:
        for r in affected.get("ranges", []) or []:
            for ev in r.get("events", []) or []:
                if "fixed" in ev:
                    return ev["fixed"]
    return None
