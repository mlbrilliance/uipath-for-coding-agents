"""Unit tests for aurora.promote (placeholder rendering + template loading)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from aurora import promote


@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    """Build a minimal template tree to load from."""
    d = tmp_path / "templates"
    d.mkdir()
    (d / "test_kind.json").write_text(json.dumps({
        "aurora": {
            "kind": "test_kind",
            "default_timeout_hours": 8,
            "default_on_timeout": "deny",
            "default_approvers_env": "TEST_APPROVERS",
            "priority": "Low",
        },
        "form": {
            "title": "AURORA test form: {{ candidate }}",
            "components": [
                {"type": "textfield", "key": "name", "defaultValue": "{{ name }}"},
                {"type": "url", "key": "diff", "defaultValue": "{{ diff_url }}"},
            ],
        },
    }), encoding="utf-8")
    return d


def test_load_template_finds_underscored_name(template_dir: Path) -> None:
    template = promote._load_template("test_kind", template_dir)
    assert template["aurora"]["kind"] == "test_kind"


def test_load_template_finds_hyphenated_fallback(template_dir: Path) -> None:
    # Rename to hyphenated and verify fallback works
    (template_dir / "test_kind.json").rename(template_dir / "test-kind.json")
    template = promote._load_template("test_kind", template_dir)
    assert template["aurora"]["kind"] == "test_kind"


def test_load_template_raises_when_missing(template_dir: Path) -> None:
    with pytest.raises(promote.GateError, match="no template"):
        promote._load_template("missing_kind", template_dir)


def test_render_placeholders_substitutes_strings() -> None:
    obj = {
        "title": "hello {{ name }}",
        "components": [
            {"key": "url", "defaultValue": "{{ diff_url }}"},
            {"key": "static", "defaultValue": "no placeholder"},
        ],
    }
    rendered = promote._render_placeholders(obj, {"name": "Alice", "diff_url": "https://x/y"})
    assert rendered["title"] == "hello Alice"
    assert rendered["components"][0]["defaultValue"] == "https://x/y"
    assert rendered["components"][1]["defaultValue"] == "no placeholder"


def test_render_placeholders_handles_missing_keys_gracefully() -> None:
    out = promote._render_placeholders({"x": "{{ unknown }}"}, {})
    assert out == {"x": ""}


def test_render_placeholders_recurses_into_lists() -> None:
    obj = {"items": ["{{ a }}", "{{ b }}", "literal"]}
    rendered = promote._render_placeholders(obj, {"a": "ALPHA", "b": "BETA"})
    assert rendered["items"] == ["ALPHA", "BETA", "literal"]
