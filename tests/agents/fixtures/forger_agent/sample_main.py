"""AURORA contract-test fixture (NOT a real agent).

Encodes the shape forger-agent promises (R.K.04, R.K.05).
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from tools import nvd, osv  # noqa: F401  — referenced for shape


class TriageInput(BaseModel):
    package: str
    version: str


class TriageOutput(BaseModel):
    severity: str
    rationale: str


PROMPT_PATH = Path(__file__).parent / "prompts/triage.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")


def main(input: dict) -> TriageOutput:
    payload = TriageInput.model_validate(input)
    return TriageOutput(severity="informational", rationale=f"stub for {payload.package}")
