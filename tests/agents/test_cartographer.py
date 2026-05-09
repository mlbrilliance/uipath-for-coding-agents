"""T-G3b — Cartographer contract test.

Loads a recorded `references.json` fixture and asserts every selector
satisfies R.SE.01 (strict / single-find) and R.SE.03 (at least one
fallback). The fixture stands in for the live Playwright-MCP capture
the agent would run on a Windows demo runner.

Satisfies US-29, US-31.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.agents.contracts.cartographer import ReferencesFile, Selector

FIXTURE = Path(__file__).parent / "fixtures" / "cartographer" / "sample_references.json"


def test_references_validate_against_contract() -> None:
    refs = ReferencesFile.model_validate(json.loads(FIXTURE.read_text()))
    assert refs.app, "every references file is keyed by app"
    assert refs.selectors, "references must contain at least one selector"


def test_every_selector_is_strict_and_has_fallback() -> None:
    refs = ReferencesFile.model_validate(json.loads(FIXTURE.read_text()))
    for sel in refs.selectors:
        assert sel.strict, f"R.SE.01: {sel.name} must be strict"
        assert len(sel.fallbacks) >= 1, f"R.SE.03: {sel.name} must declare a fallback"


def test_strict_false_is_rejected() -> None:
    with pytest.raises(ValueError, match="R.SE.01"):
        Selector.model_validate(
            {
                "name": "Bad",
                "primary": "<webctrl tag='BUTTON' />",
                "fallbacks": ["<webctrl tag='BUTTON' aaname='X' />"],
                "strict": False,
            }
        )


def test_missing_fallback_is_rejected() -> None:
    with pytest.raises(ValueError):
        Selector.model_validate(
            {
                "name": "Bad",
                "primary": "<webctrl tag='BUTTON' aaname='X' />",
                "fallbacks": [],
                "strict": True,
            }
        )
