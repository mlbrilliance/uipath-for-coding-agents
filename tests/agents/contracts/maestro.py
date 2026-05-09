"""Forger-Maestro BPMN + bindings contract.

Helpers used by `tests/agents/test_forger_maestro.py`. The two bedrock
assertions:
    1. The BPMN file must NOT contain any `<uipath:taskBinding>` element
       (T-A2 stripped these; this test is the regression guard).
    2. Every `<bpmn:serviceTask>` and `<bpmn:userTask>` `id` in the BPMN
       must have a matching key in `bindings.json::tasks`.

Discipline cited: R.M.01–R.M.06.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

BPMN_NS = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
UIPATH_NS = "http://uipath.com/maestro/2024"
TASK_BINDING_RE = re.compile(r"<\s*uipath:\s*taskBinding\b", re.IGNORECASE)


class MaestroBindings(BaseModel):
    """`bindings.json` skeleton — only fields the contract test cares about."""

    model_config = ConfigDict(extra="allow")

    process: Annotated[str, Field(min_length=1)]
    folder: Annotated[str, Field(min_length=1)]
    tasks: Annotated[dict[str, dict], Field(min_length=1)]


def assert_no_inline_task_binding(bpmn_text: str) -> None:
    """T-A2 regression guard.

    The inline `<uipath:taskBinding>` element is not part of the
    documented Studio Web schema; bindings live in `bindings.json`.
    """
    assert UIPATH_NS not in bpmn_text or "taskBinding" not in bpmn_text, (
        "BPMN must not declare uipath:taskBinding inline (see docs/grill-2026-05-09.md §D1)"
    )
    match = TASK_BINDING_RE.search(bpmn_text)
    assert match is None, (
        f"BPMN must not contain <uipath:taskBinding> (T-A2 regression); "
        f"found at offset {match.start() if match else -1}"
    )


def collect_bound_task_ids(bpmn_text: str) -> list[str]:
    """All `<bpmn:serviceTask>` and `<bpmn:userTask>` ids needing a binding."""
    root = ET.fromstring(bpmn_text)
    ids: list[str] = []
    for tag in ("serviceTask", "userTask"):
        for el in root.iter(f"{BPMN_NS}{tag}"):
            task_id = el.attrib.get("id")
            if task_id:
                ids.append(task_id)
    return ids
