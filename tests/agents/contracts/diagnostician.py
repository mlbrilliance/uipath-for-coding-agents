"""Diagnostician triage contract + offline validator.

Diagnostician's contract is a ``TriageRecord`` per fault cluster. The
``triage_from_cluster`` validator translates a recorded cluster seed into a
typed record, gating ``auto_fix`` on the policy-driven confidence floor.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_MIN_CONFIDENCE_FOR_AUTO_DISPATCH = 0.7


class TriageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: str = Field(min_length=1)
    root_cause: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    fix_hypothesis: str = Field(min_length=1)
    auto_fix: bool = False
    cluster_size: int = Field(ge=1, default=1)

    @field_validator("cluster_id")
    @classmethod
    def _strip_id(cls, v: str) -> str:
        return v.strip()


def triage_from_cluster(
    cluster: dict[str, Any],
    *,
    min_confidence_for_auto_dispatch: float = DEFAULT_MIN_CONFIDENCE_FOR_AUTO_DISPATCH,
) -> TriageRecord:
    """Build a TriageRecord from a fingerprint cluster seed.

    Confidence climbs with cluster size *and* prior-resolution count; when the
    cluster is novel (no peers, no resolutions), we ceiling at 0.45 to keep
    auto-dispatch off without HITL.
    """
    cluster_size = int(cluster.get("cluster_size", 1))
    prior_resolutions = int(cluster.get("prior_resolutions", 0))
    base = cluster.get("base_confidence")
    if base is None:
        if cluster_size <= 1 and prior_resolutions == 0:
            base = 0.30
        else:
            similarity_lift = min(0.5, 0.05 * cluster_size)
            history_lift = min(0.3, 0.10 * prior_resolutions)
            base = round(0.30 + similarity_lift + history_lift, 4)
    confidence = max(0.0, min(1.0, float(base)))
    auto_fix = confidence >= min_confidence_for_auto_dispatch
    return TriageRecord(
        cluster_id=cluster["cluster_id"],
        root_cause=cluster["root_cause"],
        confidence=confidence,
        fix_hypothesis=cluster["fix_hypothesis"],
        auto_fix=auto_fix,
        cluster_size=cluster_size,
    )
