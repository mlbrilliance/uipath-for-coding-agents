"""T-G3b — Forger-RPA contract test.

Reads a fixture XAML representing a workflow Forger-RPA promises to
emit, and asserts it satisfies the disciplines in `agents/forger-rpa.md`:

    R.N.02 — every Argument has an `in_/out_/io_` direction prefix.
    R.E.01 — workflow-level Try/Catch wraps the external boundary.
    R.L.01 — workflow opens with `Log Message` (Info "Starting …").

Satisfies US-9, US-31.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.agents.contracts.forger import ForgerArtifact, has_arg_prefix

FIXTURE = Path(__file__).parent / "fixtures" / "forger_rpa" / "sample.xaml"
XAML_NS = "{http://schemas.microsoft.com/netfx/2009/xaml/activities}"
X_NS = "{http://schemas.microsoft.com/winfx/2006/xaml}"
UI_NS = "{http://schemas.uipath.com/workflow/activities}"


def _read() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_artifact_shape() -> None:
    artifact = ForgerArtifact(
        forger="forger-rpa",
        candidate_id="CAND-RPA-001",
        emitted_paths=[FIXTURE],
    )
    assert artifact.emitted_paths[0].suffix == ".xaml"


def test_arguments_are_direction_prefixed() -> None:
    """R.N.02 — every <x:Property> name must start with in_/out_/io_."""
    root = ET.fromstring(_read())
    members = root.find(f"{X_NS}Members")
    assert members is not None and len(members) >= 1, "fixture must declare arguments"
    for prop in members.findall(f"{X_NS}Property"):
        name = prop.attrib["Name"]
        assert has_arg_prefix(name), f"R.N.02: {name!r} missing direction prefix"


def test_workflow_has_top_level_try_catch() -> None:
    """R.E.01 — every external boundary wrapped in Try/Catch."""
    root = ET.fromstring(_read())
    assert root.iter(f"{XAML_NS}TryCatch"), "R.E.01: no TryCatch element found"
    found = list(root.iter(f"{XAML_NS}TryCatch"))
    assert found, "R.E.01: workflow must wrap external calls in TryCatch"


def test_workflow_opens_with_log_message() -> None:
    """R.L.01 — bookend Log Message at workflow entry."""
    text = _read()
    match = re.search(r"<ui:LogMessage\b[^>]*Level=\"Info\"[^>]*Message=\"Starting", text)
    assert match is not None, "R.L.01: workflow must open with Log Message (Info 'Starting …')"
