"""Auditor drift-report contract + offline validator.

Auditor inspects deployed-vs-repo state and emits a ``DriftReport``: the
catalogue of idle processes, package-hash mismatches, and current license
utilisation. R.G.01/R.G.02 require this verdict to be clean before any prod
publish.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_IDLE_DAYS_THRESHOLD = 90


class IdleProcess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    last_run: datetime | None
    days_since_last_run: int = Field(ge=0)


class HashMismatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: str
    deployed_sha: str
    repo_sha: str


class LicenseUtil(BaseModel):
    model_config = ConfigDict(extra="forbid")

    used: int = Field(ge=0)
    total: int = Field(gt=0)
    pct: float = Field(ge=0.0, le=1.0)


class DriftReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idle_processes: list[IdleProcess] = Field(default_factory=list)
    hash_mismatches: list[HashMismatch] = Field(default_factory=list)
    license_util: LicenseUtil


def audit_from_dataset(
    data: dict[str, Any],
    *,
    idle_days_threshold: int = DEFAULT_IDLE_DAYS_THRESHOLD,
) -> DriftReport:
    """Translate a recorded dataset into a typed DriftReport.

    Idle-process detection (R.G.01 governance pre-publish): any process whose
    ``days_since_last_run`` exceeds the threshold is surfaced. Package-hash
    drift (R.G.02): every package with a non-matching deployed/repo SHA is
    listed for redeploy or back-port.
    """
    idle: list[IdleProcess] = []
    for proc in data.get("processes", []):
        days = int(proc.get("days_since_last_run", 0))
        if days > idle_days_threshold:
            idle.append(
                IdleProcess(
                    name=proc["name"],
                    last_run=proc.get("last_run"),
                    days_since_last_run=days,
                )
            )

    mismatches: list[HashMismatch] = []
    for pkg in data.get("packages", []):
        if pkg["deployed_sha"] != pkg["repo_sha"]:
            mismatches.append(HashMismatch(**pkg))

    lic = data["license"]
    used = int(lic["used"])
    total = int(lic["total"])
    license_util = LicenseUtil(used=used, total=total, pct=round(used / total, 4))

    return DriftReport(
        idle_processes=idle,
        hash_mismatches=mismatches,
        license_util=license_util,
    )
