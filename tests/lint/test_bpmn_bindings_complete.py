"""Asserts every executable BPMN task in process.bpmn has a matching
binding entry in bindings.json.

After the T-A2 cleanup (resolution D1), bindings.json is the only source
of truth for binding metadata. Any task in the BPMN without a binding
will fail at deploy time. This test catches that drift before it ships.

Acceptance test for T-A2.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO = REPO_ROOT / "examples" / "oss-supply-chain-defender"
PROCESS_BPMN = DEMO / "process.bpmn"
BINDINGS = DEMO / "bindings.json"

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

# BPMN element types that carry runtime behaviour (need a binding entry).
EXECUTABLE_TASK_TYPES = {
    "serviceTask",
    "userTask",
    "scriptTask",
    "businessRuleTask",
    "sendTask",
    "receiveTask",
}


def _ids_of_executable_tasks() -> set[str]:
    tree = ET.parse(PROCESS_BPMN)
    out: set[str] = set()
    for elem in tree.iter():
        if not elem.tag.startswith("{" + BPMN_NS + "}"):
            continue
        local = elem.tag.split("}", 1)[1]
        if local in EXECUTABLE_TASK_TYPES:
            tid = elem.get("id")
            if tid:
                out.add(tid)
    return out


def _binding_keys() -> set[str]:
    data = json.loads(BINDINGS.read_text(encoding="utf-8"))
    return set(data.get("tasks", {}).keys())


def test_every_executable_task_has_binding() -> None:
    bpmn_ids = _ids_of_executable_tasks()
    binding_keys = _binding_keys()
    missing = bpmn_ids - binding_keys
    assert not missing, (
        "BPMN tasks without bindings.json entry: " + ", ".join(sorted(missing))
    )


def test_no_orphan_bindings() -> None:
    """A binding entry whose task id no longer exists in the BPMN is dead code."""
    bpmn_ids = _ids_of_executable_tasks()
    binding_keys = _binding_keys()
    orphans = binding_keys - bpmn_ids
    assert not orphans, (
        "bindings.json has entries for non-existent BPMN tasks: "
        + ", ".join(sorted(orphans))
    )


def test_message_definitions_match_receive_tasks() -> None:
    """Every receiveTask referencing a message must have it defined."""
    tree = ET.parse(PROCESS_BPMN)
    receive_ids = [
        elem.get("id")
        for elem in tree.iter("{" + BPMN_NS + "}receiveTask")
    ]
    if not receive_ids:
        return  # no receive tasks; trivially satisfied
    data = json.loads(BINDINGS.read_text(encoding="utf-8"))
    msg_defs = data.get("messageDefinitions", {})
    tasks = data.get("tasks", {})
    for rid in receive_ids:
        binding = tasks.get(rid, {})
        if binding.get("kind") != "message-receive":
            continue
        msg = binding.get("message")
        assert msg in msg_defs, (
            f"receiveTask {rid} references message '{msg}' not defined "
            f"in bindings.json::messageDefinitions"
        )


def test_bindings_schema_top_level_keys() -> None:
    """Sanity: bindings.json keeps its top-level shape after T-A2."""
    data = json.loads(BINDINGS.read_text(encoding="utf-8"))
    for key in ["process", "folder", "version", "tasks", "decisions",
                "messageDefinitions", "variables", "endEvents"]:
        assert key in data, f"bindings.json missing top-level key: {key}"
