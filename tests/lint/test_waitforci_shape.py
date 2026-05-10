"""Regression test: WaitForCI uses Send Task + intermediate message catch
+ boundary timer — NOT a Receive Task (which is execution-illegal in Maestro).

Per docs/grill-2026-05-09.md (resolution D2), the primary path replaces
<bpmn:receiveTask id="WaitForCI"> with a three-element BPMN pattern:
  1. Send Task (PostPendingComment) — posts an audit-trail comment.
  2. Intermediate message catch event (WaitForCI) — pauses until CI webhook
     fires, correlated by pr_url (T-D1 contract).
  3. Boundary timer — bounded wait; on timeout, route to needs-human path.

Acceptance test for T-D2.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
}
BPMN = Path(__file__).resolve().parents[2] / "examples" / "oss-supply-chain-defender" / "process.bpmn"
BINDINGS = BPMN.parent / "bindings.json"


def _root() -> ET.Element:
    return ET.parse(BPMN).getroot()


def test_no_receivetask_with_id_waitforci() -> None:
    """Receive Task is execution-illegal in Maestro per docs/grill-2026-05-09.md."""
    receive_tasks = _root().findall(".//bpmn:receiveTask", NS)
    ids = [t.get("id") for t in receive_tasks]
    assert "WaitForCI" not in ids, f"WaitForCI still a Receive Task: {ids}"


def test_send_task_posts_pending_comment() -> None:
    send_tasks = _root().findall(".//bpmn:sendTask", NS)
    ids = [t.get("id") for t in send_tasks]
    assert "PostPendingComment" in ids


def test_intermediate_catch_event_for_ci_result_exists() -> None:
    catches = _root().findall(".//bpmn:intermediateCatchEvent", NS)
    catch = next((c for c in catches if c.get("id") == "WaitForCI"), None)
    assert catch is not None, "WaitForCI must be an intermediateCatchEvent"
    msg_def = catch.find("bpmn:messageEventDefinition", NS)
    assert msg_def is not None, "WaitForCI must have a messageEventDefinition"


def test_boundary_timer_on_waitforci() -> None:
    """A boundary timer attached to the catch event with a non-zero duration."""
    boundaries = _root().findall(".//bpmn:boundaryEvent", NS)
    relevant = [b for b in boundaries if b.get("attachedToRef") == "WaitForCI"]
    assert relevant, "no boundary timer attached to WaitForCI"
    timer_def = relevant[0].find("bpmn:timerEventDefinition", NS)
    assert timer_def is not None, "boundary event must be a timer"
    duration = timer_def.find("bpmn:timeDuration", NS)
    assert duration is not None and duration.text, "timer needs timeDuration"
    assert duration.text.startswith("PT") or duration.text.startswith("P"), \
        f"ISO 8601 duration expected, got {duration.text!r}"


def test_correlation_key_is_pr_url() -> None:
    """The catch event's data-input or message ref must mention pr_url
    (matches T-D1's outbound correlation key convention)."""
    text = BPMN.read_text()
    assert "pr_url" in text, "correlation key 'pr_url' missing — T-D1 contract"


def test_bindings_json_has_post_pending_comment_binding() -> None:
    bindings = json.loads(BINDINGS.read_text())
    assert "PostPendingComment" in bindings.get("tasks", {})
    entry = bindings["tasks"]["PostPendingComment"]
    assert entry.get("kind") == "coded-workflow"
    assert entry.get("entry") == "GitHub.PostPendingComment.PostPendingComment"
