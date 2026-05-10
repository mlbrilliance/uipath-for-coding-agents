"""Pydantic models for the AuroraVulnLookup agent.

These define the contract between Maestro tasks and the agent. The DMN
severity matrix and downstream tasks read these field names verbatim;
don't rename without coordinating with Forger-Maestro.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LockfileEntry(BaseModel):
    """A single dependency line from a lockfile."""
    ecosystem: str = Field(..., description="npm | pypi | go | rubygems | maven | cargo")
    name: str
    version: str
    depth: int = Field(default=1, description="1=direct, 2+=transitive")


class Lockfile(BaseModel):
    repo: str
    ecosystem: str
    deps: list[LockfileEntry]


class LockfileBatch(BaseModel):
    """Input shape for the bulk vuln-lookup task."""
    lockfiles: list[Lockfile]


class Finding(BaseModel):
    """Single advisory match against a dependency."""
    ecosystem: str
    package: str
    version: str
    depth: int = 1
    advisory_id: str = Field(..., description="CVE-YYYY-NNNN, GHSA-..., OSV-...")
    title: str = ""
    cvss: float | None = None
    exploit_in_wild: bool = False
    fix_version: str | None = None
    source: str = Field(..., description="nvd | osv | github-advisory")
    url: str | None = None


class TriageInput(BaseModel):
    """Input for the deep-triage task in the Critical sub-process."""
    findings: list[Finding]


class RemediationDiff(BaseModel):
    """Concrete diff proposal for the auto-PR step."""
    files: list[dict] = Field(default_factory=list, description="[{path, before, after}]")
    files_touched: int = 0
    url: str | None = None  # set after the PR is opened


class TriageResult(BaseModel):
    triage_summary: str = ""
    proposed_diff: RemediationDiff | None = None
