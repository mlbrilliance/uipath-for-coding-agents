"""T-G3a — Curator output contract tests.

Two recorded fixtures exercise the dedup decision documented in
``agents/curator.md``:

* ``dup_signal.json``  — close to existing backlog (similarity > 0.85)
                         → emits ``{decision: 'merge',  candidate_id: 'C-…'}``
* ``new_signal.json``  — no cluster match
                         → emits ``{decision: 'create', candidate_id: 'C-…'}``

R.T.01: each test maps to a curator acceptance rule (dedup-rules 1-4).
R.T.02: contract is asserted, not the code path.
R.T.04: includes both decision branches; negative shape is enforced via
        the ``BacklogEntry`` model's ``Literal`` decision and id pattern.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from tests.agents.contracts.curator import BacklogEntry, curate_signal

FIXTURES = Path(__file__).parent / "fixtures" / "curator"


def _load(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_curator_dup_signal_yields_merge_decision() -> None:
    payload = _load("dup_signal.json")
    entry = curate_signal(payload)
    assert isinstance(entry, BacklogEntry)
    assert entry.decision == "merge"
    assert entry.candidate_id == payload["matched_candidate_id"]
    assert entry.candidate_id.startswith("C")
    assert entry.similarity > 0.85, "merge branch requires similarity > 0.85"
    assert entry.mentions == payload["existing_mentions"] + 1


def test_curator_new_signal_yields_create_decision() -> None:
    payload = _load("new_signal.json")
    entry = curate_signal(payload)
    assert isinstance(entry, BacklogEntry)
    assert entry.decision == "create"
    assert entry.candidate_id == payload["new_candidate_id"]
    assert entry.candidate_id.startswith("C")
    assert entry.similarity <= 0.85, "create branch requires similarity ≤ 0.85"
    assert entry.mentions == 1


@pytest.mark.parametrize(
    "fixture_name,expected_decision",
    [("dup_signal.json", "merge"), ("new_signal.json", "create")],
    ids=["dup", "new"],
)
def test_curator_decision_is_in_closed_set(
    fixture_name: str, expected_decision: str
) -> None:
    entry = curate_signal(_load(fixture_name))
    assert entry.decision in {"merge", "create"}
    assert entry.decision == expected_decision
