"""Curator contract — BacklogEntry decision.

Mirrors the dedup decision Curator emits per `agents/curator.md`. The
agent itself rewrites `.aurora/backlog.md`; the structured artefact this
test suite asserts on is the per-signal *decision* (``merge`` vs
``create``) plus the resulting candidate id.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CANDIDATE_ID_RE = re.compile(r"^C(?:AND)?-[A-Za-z0-9-]+$")

CURATOR_DUP_THRESHOLD = 0.85


class BacklogEntry(BaseModel):
    """The structured decision Curator emits per inbound Scout signal."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["merge", "create"]
    candidate_id: str = Field(min_length=3)
    cluster: str = Field(min_length=1)
    similarity: float = Field(ge=0.0, le=1.0)
    mentions: int = Field(ge=1)

    @field_validator("candidate_id")
    @classmethod
    def _candidate_id_shape(cls, value: str) -> str:
        if not CANDIDATE_ID_RE.match(value):
            raise ValueError(
                f"candidate_id {value!r} must match {CANDIDATE_ID_RE.pattern}"
            )
        return value


def curate_signal(payload: dict[str, Any]) -> BacklogEntry:
    """Deterministic shim mirroring Curator's dedup rules.

    Inputs are already-flattened Scout signals plus a recorded similarity
    score against the existing backlog (so the test stays deterministic
    and offline). Per ``agents/curator.md``:

    * similarity > 0.85 → merge into the matched candidate
    * otherwise         → create a fresh candidate
    """
    similarity = float(payload["similarity"])
    if similarity > CURATOR_DUP_THRESHOLD:
        return BacklogEntry(
            decision="merge",
            candidate_id=payload["matched_candidate_id"],
            cluster=payload["cluster"],
            similarity=similarity,
            mentions=int(payload.get("existing_mentions", 1)) + 1,
        )
    return BacklogEntry(
        decision="create",
        candidate_id=payload["new_candidate_id"],
        cluster=payload["cluster"],
        similarity=similarity,
        mentions=1,
    )
