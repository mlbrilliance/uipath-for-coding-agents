"""T-G3a — Scout output contract tests.

Loads the recorded Slack and Jira fixtures, runs the deterministic
``parse_friction_signal`` shim, and asserts the result validates against
``FrictionSignal``. A negative fixture proves the validator rejects
malformed input (R.T.04 — error-path tests are mandatory).

Maps to acceptance criteria of `agents/scout.md`:

* "emit a JSON object on stdout that `curator` will consume" — shape test
* "Phrases of frequency: 'every Monday', 'weekly'…" — frequency_hint enum

R.T.01: each test maps to an agent acceptance criterion.
R.T.02: tests assert the contract, not the code path.
R.T.03: no external services to mock — these are offline contract tests.
R.T.04: includes the negative ``malformed.json`` case.
R.SEC R.X.04: no `ANTHROPIC_API_KEY` referenced anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from tests.agents.contracts.scout import FrictionSignal, parse_friction_signal

FIXTURES = Path(__file__).parent / "fixtures" / "scout"


def _load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text(encoding="utf-8")))


@pytest.mark.parametrize(
    "fixture_name",
    ["slack_pmo.json", "jira_export.json"],
    ids=["slack", "jira"],
)
def test_scout_signal_validates_against_friction_signal(fixture_name: str) -> None:
    payload = _load(fixture_name)
    signal = parse_friction_signal(payload)
    assert isinstance(signal, FrictionSignal)
    assert signal.source.startswith(("slack:", "jira:")), (
        f"{fixture_name}: source must carry a known provenance prefix; "
        f"got {signal.source!r}"
    )
    assert signal.text, f"{fixture_name}: text must be non-empty"
    assert signal.actor, f"{fixture_name}: actor must be non-empty"


def test_scout_frequency_hint_is_enum_constrained() -> None:
    payload = _load("slack_pmo.json")
    signal = parse_friction_signal(payload)
    assert signal.frequency_hint in {
        "daily", "weekly", "monthly", "quarterly", "ad-hoc", "unknown"
    }


def test_scout_validator_rejects_malformed_payload() -> None:
    payload = _load("malformed.json")
    with pytest.raises(ValidationError) as exc:
        parse_friction_signal(payload)
    errors = exc.value.errors()
    assert errors, "expected at least one ValidationError"
    error_locs = {".".join(str(p) for p in err["loc"]) for err in errors}
    assert error_locs & {"source", "text", "frequency_hint", "actor", "timestamp"}, (
        f"expected a violation on a documented FrictionSignal field; got {error_locs}"
    )
