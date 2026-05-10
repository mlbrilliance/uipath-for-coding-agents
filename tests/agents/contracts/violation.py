"""Pydantic model emitted by the Reviewer-style heuristic lint (T-G4).

Every rule under :mod:`tests.agents.reviewer_rules` returns a list of
:class:`Violation` objects. The lint runs offline (no LLM calls) and is
parametrised over every ``agents/<name>.md`` file by
``tests/agents/test_all_agents_lint.py``.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Severity = Literal["error", "warning", "info"]


class Violation(BaseModel):
    rule_id: str
    severity: Severity
    agent: str
    line: int | None = None
    message: str

    def __str__(self) -> str:
        loc = f":{self.line}" if self.line is not None else ""
        return f"[{self.severity.upper()}] {self.rule_id} {self.agent}{loc} — {self.message}"
