"""Pydantic models for the AuroraMaintainerHealth agent.

These define the contract between the Maestro `MaintainerHealth` task
and the agent. Field names are read verbatim by the DMN severity matrix
and the digest builder; don't rename without coordinating with
Forger-Maestro.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------- Inputs ----------
# We redefine LockfileEntry/Lockfile inline rather than importing from the
# sibling vuln-lookup agent: each Coded Agent is its own UiPath package,
# and `uipath pack` only sees files in *this* directory. Cross-agent imports
# would silently work locally and explode at deploy time.

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


class MaintainerHealthInput(BaseModel):
    """Input shape for the MaintainerHealth Maestro task."""
    lockfiles: list[Lockfile]


# ---------- Outputs ----------

class PackageHealth(BaseModel):
    """Health signal for a single dependency."""
    ecosystem: str
    name: str
    version: str
    scorecard_score: Optional[float] = Field(
        default=None,
        description="OpenSSF Scorecard aggregate score (0-10). None if API has no data.",
    )
    commit_recency_days: Optional[int] = Field(
        default=None,
        description="Days since the most recent commit on the default branch. None if unknown.",
    )
    health_score: float = Field(
        ...,
        description="AURORA-derived 0-10 health score combining scorecard + recency.",
        ge=0.0,
        le=10.0,
    )
    flags: list[str] = Field(
        default_factory=list,
        description="Risk markers, e.g. 'stale', 'low-scorecard', 'no-scorecard'.",
    )


class MaintainerHealthReport(BaseModel):
    """Aggregate output for the Maestro task."""
    packages: list[PackageHealth]
    aggregate_score: float = Field(..., ge=0.0, le=10.0)
    flagged_count: int = Field(..., ge=0)
