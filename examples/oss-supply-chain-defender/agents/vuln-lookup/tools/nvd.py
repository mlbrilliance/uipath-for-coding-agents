"""NVD (National Vulnerability Database) lookup.

Public REST API: https://services.nvd.nist.gov/rest/json/cves/2.0
Anonymous works at 5 req/30s; with NVD_API_KEY set, 50 req/30s.

Uses CPE matching to filter results to specific (vendor, product, version)
combinations. CPE strings are heuristic; for the demo we generate them
from ecosystem + package name.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from models import Finding, LockfileEntry

logger = logging.getLogger(__name__)

NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"


def _cpe_for(dep: LockfileEntry) -> str:
    """Heuristic CPE generator. Real production code would use a CPE dictionary."""
    vendor = {
        "npm": dep.name.split("/")[0] if "/" in dep.name else dep.name,
        "pypi": dep.name,
        "go": dep.name.split("/")[-1] if "/" in dep.name else dep.name,
    }.get(dep.ecosystem, dep.name)
    product = dep.name.split("/")[-1]
    return f"cpe:2.3:a:{vendor}:{product}:{dep.version}:*:*:*:*:*:*:*"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def lookup(dep: LockfileEntry) -> list[Finding]:
    """Query NVD for CVEs matching this dep. Empty list on no match."""
    headers = {}
    if api_key := os.environ.get("NVD_API_KEY"):
        headers["apiKey"] = api_key

    params = {
        "cpeName": _cpe_for(dep),
        "resultsPerPage": 20,
    }

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(NVD_BASE, params=params, headers=headers)
        if r.status_code != 200:
            logger.warning("nvd: HTTP %d for %s", r.status_code, dep.name)
            return []
        data = r.json()
    except httpx.HTTPError as e:
        logger.warning("nvd: %s", e)
        return []

    findings: list[Finding] = []
    for item in data.get("vulnerabilities", []):
        cve = item.get("cve", {})
        cve_id = cve.get("id", "")
        descriptions = cve.get("descriptions", [])
        title = next(
            (d.get("value", "") for d in descriptions if d.get("lang") == "en"),
            "",
        )

        cvss = _extract_max_cvss(cve)
        exploit = _has_known_exploit(cve)

        findings.append(Finding(
            ecosystem=dep.ecosystem,
            package=dep.name,
            version=dep.version,
            depth=dep.depth,
            advisory_id=cve_id,
            title=title[:200],
            cvss=cvss,
            exploit_in_wild=exploit,
            source="nvd",
            url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
        ))

    return findings


def _extract_max_cvss(cve: dict) -> Optional[float]:
    metrics = cve.get("metrics", {})
    scores: list[float] = []
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        for m in metrics.get(key, []):
            data = m.get("cvssData", {})
            score = data.get("baseScore")
            if isinstance(score, (int, float)):
                scores.append(float(score))
    return max(scores) if scores else None


def _has_known_exploit(cve: dict) -> bool:
    """NVD doesn't expose exploit-in-wild directly; we approximate via CISA KEV refs."""
    refs = cve.get("references", []) or []
    for r in refs:
        url = (r.get("url") or "").lower()
        if "kev" in url or "cisa.gov" in url or "exploit-db" in url:
            return True
    return False
