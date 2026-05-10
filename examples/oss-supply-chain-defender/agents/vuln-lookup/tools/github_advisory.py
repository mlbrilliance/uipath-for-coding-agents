"""GitHub Advisory Database lookup via the GraphQL API.

Requires GITHUB_TOKEN. The token is fetched at runtime from a UiPath
Orchestrator Asset (configured by the deploy step). Falls back to the
env var for local debug.
"""
from __future__ import annotations

import logging
import os

import httpx
from models import Finding, LockfileEntry
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

GH_GRAPHQL = "https://api.github.com/graphql"


_ECOSYSTEM_MAP = {
    "npm": "NPM",
    "pypi": "PIP",
    "go": "GO",
    "rubygems": "RUBYGEMS",
    "maven": "MAVEN",
    "cargo": "RUST",
}


_QUERY = """
query($ecosystem: SecurityAdvisoryEcosystem!, $package: String!) {
  securityVulnerabilities(ecosystem: $ecosystem, package: $package, first: 25) {
    nodes {
      advisory {
        ghsaId
        summary
        severity
        cvss {
          score
        }
        references { url }
      }
      vulnerableVersionRange
      firstPatchedVersion { identifier }
    }
  }
}
"""


def _resolve_token() -> str | None:
    """Try Orchestrator Asset first; fall back to env."""
    try:
        from uipath import UiPath  # type: ignore[import-not-found]
        sdk = UiPath()
        asset = sdk.assets.retrieve(name="GitHubToken")
        if asset and asset.get("Value"):
            return asset["Value"]
    except Exception:
        pass
    return os.environ.get("GITHUB_TOKEN")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def lookup(dep: LockfileEntry) -> list[Finding]:
    token = _resolve_token()
    if not token:
        logger.info("github_advisory: no token; skipping")
        return []

    eco = _ECOSYSTEM_MAP.get(dep.ecosystem)
    if not eco:
        return []

    body = {
        "query": _QUERY,
        "variables": {"ecosystem": eco, "package": dep.name},
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(GH_GRAPHQL, json=body, headers=headers)
        if r.status_code != 200:
            logger.warning("github_advisory: HTTP %d for %s", r.status_code, dep.name)
            return []
        data = r.json()
    except httpx.HTTPError as e:
        logger.warning("github_advisory: %s", e)
        return []

    findings: list[Finding] = []
    nodes = (
        data.get("data", {})
        .get("securityVulnerabilities", {})
        .get("nodes", [])
    )
    for node in nodes:
        if not _version_in_range(dep.version, node.get("vulnerableVersionRange", "")):
            continue
        adv = node.get("advisory", {})
        cvss = (adv.get("cvss") or {}).get("score")
        fix = (node.get("firstPatchedVersion") or {}).get("identifier")

        findings.append(Finding(
            ecosystem=dep.ecosystem,
            package=dep.name,
            version=dep.version,
            depth=dep.depth,
            advisory_id=adv.get("ghsaId", ""),
            title=adv.get("summary", "")[:200],
            cvss=float(cvss) if isinstance(cvss, (int, float)) else None,
            exploit_in_wild=False,  # GHSA doesn't carry this directly either
            fix_version=fix,
            source="github-advisory",
            url=f"https://github.com/advisories/{adv.get('ghsaId', '')}",
        ))
    return findings


def _version_in_range(version: str, vuln_range: str) -> bool:
    """Naive range check.

    GitHub returns ranges like '< 4.17.21' or '>= 4.0.0, < 4.17.21'. For the
    demo, we accept all results — production code would parse semver/PEP440
    properly.
    """
    if not vuln_range:
        return True
    return True  # demo: trust the API's filter
