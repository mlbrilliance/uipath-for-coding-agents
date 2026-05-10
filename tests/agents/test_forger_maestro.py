"""T-G3b — Forger-Maestro contract test.

The high-stakes BPMN regression guard. Two fixtures (`sample_process.bpmn`,
`sample_bindings.json`) and three assertions:

    1. T-A2 regression: NO `<uipath:taskBinding>` element survives in the
       BPMN. That extension is not in the documented Studio Web schema;
       all binding metadata lives in `bindings.json`.
    2. Every `<bpmn:serviceTask>` and `<bpmn:userTask>` `id` has a
       matching key in `bindings.json::tasks`.
    3. Every `<bpmn:userTask>` is paired with a boundary timer (R.M.02).

Satisfies US-28, supports US-43.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.agents.contracts.maestro import (
    BPMN_NS,
    MaestroBindings,
    assert_no_inline_task_binding,
    collect_bound_task_ids,
)

FIXTURES = Path(__file__).parent / "fixtures" / "forger_maestro"
BPMN_PATH = FIXTURES / "sample_process.bpmn"
BINDINGS_PATH = FIXTURES / "sample_bindings.json"


@pytest.fixture(scope="module")
def bpmn_text() -> str:
    return BPMN_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def bindings() -> MaestroBindings:
    return MaestroBindings.model_validate(json.loads(BINDINGS_PATH.read_text()))


def test_no_inline_task_binding(bpmn_text: str) -> None:
    """T-A2 regression: `<uipath:taskBinding>` is gone for good."""
    assert_no_inline_task_binding(bpmn_text)


def test_inline_task_binding_detector_catches_violation() -> None:
    """Negative control: the regression detector actually fires when it should."""
    poisoned = (
        '<bpmn:serviceTask id="X" xmlns:uipath="http://uipath.com/maestro/2024">'
        '<uipath:taskBinding package="x" />'
        '</bpmn:serviceTask>'
    )
    with pytest.raises(AssertionError):
        assert_no_inline_task_binding(poisoned)


def test_every_task_id_has_a_binding(bpmn_text: str, bindings: MaestroBindings) -> None:
    """R.M.04: every service/user task must point at a deployed package."""
    bound = collect_bound_task_ids(bpmn_text)
    assert bound, "fixture should declare at least one serviceTask or userTask"
    missing = [tid for tid in bound if tid not in bindings.tasks]
    assert not missing, f"task ids without a binding: {missing}"


def test_user_tasks_have_boundary_timer(bpmn_text: str) -> None:
    """R.M.02: every User Task ships with an attached timer event."""
    root = ET.fromstring(bpmn_text)
    user_tasks = list(root.iter(f"{BPMN_NS}userTask"))
    assert user_tasks, "fixture must include at least one userTask"
    user_task_ids = {ut.attrib["id"] for ut in user_tasks}
    timer_attached_to: set[str] = set()
    for boundary in root.iter(f"{BPMN_NS}boundaryEvent"):
        if boundary.find(f"{BPMN_NS}timerEventDefinition") is not None:
            attached = boundary.attrib.get("attachedToRef")
            if attached:
                timer_attached_to.add(attached)
    missing_timers = user_task_ids - timer_attached_to
    assert not missing_timers, (
        f"R.M.02: userTask(s) without boundary timer: {sorted(missing_timers)}"
    )


def test_bindings_shape(bindings: MaestroBindings) -> None:
    """Bindings JSON declares the process, folder, and a non-empty task map."""
    assert bindings.process == "SampleProcess"
    assert bindings.folder
    assert len(bindings.tasks) >= 2
