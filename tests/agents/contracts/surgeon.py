"""Surgeon dispatch contract + offline validator.

Surgeon receives a triage record and produces a ``FixDispatch`` describing
the in-flight repair. R.G.04 caps the blast radius: fixes that touch more
than ``policy.operate.surgeon.max_workflows_touched_without_hitl`` workflows
are forced through the HITL gate.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BusinessException(Exception):  # noqa: N818 — name mandated by R.E.04
    """Raised when an external boundary failure must surface as business-level.

    Per R.E.04, we only catch ``System.Exception`` (in coded workflows) when
    we rethrow as ``BusinessException`` with context. Surgeon's dispatcher
    follows the same rule when wrapping triage parsing failures.
    """


class FixDispatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_paths_touched: list[str] = Field(default_factory=list)
    pr_number: int | None = None
    hitl_required: bool = False


def dispatch_from_triage(
    triage: dict[str, Any],
    *,
    max_workflows_touched_without_hitl: int,
) -> FixDispatch:
    """Translate a triage record into a FixDispatch.

    R.G.04: if the patch touches more workflows than the cap, force HITL —
    even when Diagnostician's confidence was high.
    """
    try:
        paths = list(triage.get("workflow_paths_touched") or [])
    except TypeError as exc:
        raise BusinessException(f"malformed workflow_paths_touched: {exc}") from exc

    over_cap = len(paths) > max_workflows_touched_without_hitl
    forced_hitl = bool(triage.get("force_hitl"))
    auto_fix = bool(triage.get("auto_fix", True))

    hitl_required = over_cap or forced_hitl or not auto_fix

    pr_number = triage.get("pr_number")
    if pr_number is not None:
        pr_number = int(pr_number)

    return FixDispatch(
        workflow_paths_touched=paths,
        pr_number=pr_number,
        hitl_required=hitl_required,
    )
