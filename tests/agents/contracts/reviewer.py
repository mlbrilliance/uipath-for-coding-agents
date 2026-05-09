"""Reviewer LintResult contract.

Reviewer's job is to emit ERROR/WARN/INFO findings against the rules
catalogue. The contract test asserts:
    - clean fixture → `errors == []`
    - violation fixture → ≥ 1 error citing the violated rule id
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"


class LintFinding(BaseModel):
    """Single comment in `review.md`."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity
    rule: Annotated[str, Field(pattern=r"^R\.[A-Z]+\.\d+(\.\d+)?$")]
    path: Annotated[str, Field(min_length=1)]
    message: Annotated[str, Field(min_length=1)]


class LintResult(BaseModel):
    """Reviewer's verdict bundle."""

    model_config = ConfigDict(extra="forbid")

    errors: list[LintFinding] = Field(default_factory=list)
    warnings: list[LintFinding] = Field(default_factory=list)
    info: list[LintFinding] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.errors
