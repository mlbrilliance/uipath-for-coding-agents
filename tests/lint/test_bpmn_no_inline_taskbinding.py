"""Asserts process.bpmn carries no UiPath extension elements.

Per resolution D1 in docs/grill-2026-05-09.md, every binding-time piece of
metadata that earlier drafts encoded as <uipath:*> XML extension elements
now lives in bindings.json. Studio Web imports the BPMN without choking on
unknown extensions; `uipath-platform` reads bindings.json at deploy time.

This test enforces the rule: every .bpmn file under examples/ is plain
BPMN 2.0 — no xmlns:uipath namespace declaration, no <uipath:*> elements.

Acceptance test for T-A2.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"

UIPATH_NS = "http://uipath.com/maestro/2024"
UIPATH_NAMESPACE_DECL = re.compile(r'xmlns:uipath\s*=\s*["\']http://uipath\.com/[^"\']*["\']')


def _bpmn_files() -> list[Path]:
    return sorted(EXAMPLES_DIR.rglob("*.bpmn"))


def test_no_uipath_namespace_declaration_in_any_bpmn() -> None:
    offenders: list[str] = []
    for bpmn in _bpmn_files():
        text = bpmn.read_text(encoding="utf-8")
        if UIPATH_NAMESPACE_DECL.search(text):
            offenders.append(bpmn.relative_to(REPO_ROOT).as_posix())
    assert not offenders, (
        "BPMN files still declare xmlns:uipath: " + ", ".join(offenders)
    )


def test_no_uipath_elements_in_any_bpmn() -> None:
    offenders: list[tuple[str, str]] = []
    for bpmn in _bpmn_files():
        tree = ET.parse(bpmn)
        for elem in tree.iter():
            if elem.tag.startswith("{" + UIPATH_NS + "}"):
                tag = elem.tag.split("}", 1)[1]
                offenders.append(
                    (bpmn.relative_to(REPO_ROOT).as_posix(), tag)
                )
            for attr_name in elem.attrib:
                if attr_name.startswith("{" + UIPATH_NS + "}"):
                    name = attr_name.split("}", 1)[1]
                    offenders.append(
                        (bpmn.relative_to(REPO_ROOT).as_posix(), f"@{name}")
                    )
    assert not offenders, (
        "BPMN files still contain <uipath:*> elements/attributes:\n"
        + "\n".join(f"  {f}: {tag}" for f, tag in offenders)
    )


def test_taskbinding_elements_specifically_absent() -> None:
    """Belt-and-braces: the literal <uipath:taskBinding string is gone."""
    offenders: list[str] = []
    for bpmn in _bpmn_files():
        text = bpmn.read_text(encoding="utf-8")
        if "<uipath:taskBinding" in text or "<uipath:dmnBinding" in text:
            offenders.append(bpmn.relative_to(REPO_ROOT).as_posix())
    assert not offenders, (
        "Stray <uipath:taskBinding/dmnBinding still present in: "
        + ", ".join(offenders)
    )
