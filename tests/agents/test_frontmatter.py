"""T-G1 — Agent frontmatter schema + parametrised pytest.

Validates the YAML frontmatter at the top of every `agents/<name>.md`
file against `tests/schemas/agent_frontmatter.schema.json`.

This task validates **frontmatter shape only**; T-G2 covers the
prompt-body invariants (no banned phrases, cited skills exist on disk,
etc.).

Satisfies US-31.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
AGENTS_DIR = ROOT / "agents"
SCHEMA_PATH = ROOT / "tests" / "schemas" / "agent_frontmatter.schema.json"

EXPECTED_AGENT_COUNT = 19
EXPECTED_FLEET_DISTRIBUTION = {
    "discovery": 5,
    "build": 8,
    "operate": 5,
    "meta": 1,
}
VALID_FLEETS = set(EXPECTED_FLEET_DISTRIBUTION)
VALID_MODEL_TIERS = {"high_stakes", "mid_stakes", "continuous"}


def _agent_files() -> list[Path]:
    return sorted(AGENTS_DIR.glob("*.md"))


def _split_frontmatter(text: str) -> str:
    """Extract the YAML block between the first pair of `---` fences.

    Returns the raw YAML string (no fences). Raises AssertionError if
    the file does not start with a frontmatter fence.
    """
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "file must start with `---` frontmatter fence"
    body: list[str] = []
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        body.append(line)
    assert closed, "frontmatter fence not closed with a second `---`"
    yaml_block = "\n".join(body).strip()
    assert yaml_block, "frontmatter block is empty"
    return yaml_block


def _load_frontmatter(path: Path) -> dict[str, Any]:
    yaml_block = _split_frontmatter(path.read_text(encoding="utf-8"))
    data = yaml.safe_load(yaml_block)
    assert isinstance(data, dict), f"{path.name}: frontmatter must be a YAML mapping"
    return data


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


# --- sentinel tests -------------------------------------------------------


def test_count_of_agents_is_19() -> None:
    """Sentinel: catch silent additions/removals of agent definitions."""
    files = _agent_files()
    assert len(files) == EXPECTED_AGENT_COUNT, (
        f"expected exactly {EXPECTED_AGENT_COUNT} agent files, found {len(files)}: "
        f"{[p.name for p in files]}"
    )


def test_fleet_distribution() -> None:
    """Discovery 5, Build 8, Operate 5, Meta 1 — the canonical AURORA shape."""
    counts: Counter[str] = Counter()
    for path in _agent_files():
        fm = _load_frontmatter(path)
        counts[fm["fleet"]] += 1
    assert dict(counts) == EXPECTED_FLEET_DISTRIBUTION, (
        f"fleet distribution mismatch: got {dict(counts)}, "
        f"expected {EXPECTED_FLEET_DISTRIBUTION}"
    )


# --- per-agent parametrised tests -----------------------------------------


@pytest.mark.parametrize(
    "agent_path",
    _agent_files(),
    ids=lambda p: p.name,
)
class TestPerAgent:
    def test_every_agent_has_frontmatter(self, agent_path: Path) -> None:
        text = agent_path.read_text(encoding="utf-8")
        yaml_block = _split_frontmatter(text)
        # parsed body must be a non-empty mapping
        data = yaml.safe_load(yaml_block)
        assert isinstance(data, dict) and data, (
            f"{agent_path.name}: frontmatter must be a non-empty YAML mapping"
        )

    def test_frontmatter_validates_against_schema(
        self, agent_path: Path, schema: dict[str, Any]
    ) -> None:
        fm = _load_frontmatter(agent_path)
        jsonschema.validate(instance=fm, schema=schema)

    def test_name_matches_filename(self, agent_path: Path) -> None:
        fm = _load_frontmatter(agent_path)
        assert fm["name"] == agent_path.stem, (
            f"{agent_path.name}: frontmatter name {fm['name']!r} "
            f"must equal filename stem {agent_path.stem!r}"
        )

    def test_fleet_field_present_and_valid(self, agent_path: Path) -> None:
        fm = _load_frontmatter(agent_path)
        assert "fleet" in fm, f"{agent_path.name}: missing `fleet`"
        assert fm["fleet"] in VALID_FLEETS, (
            f"{agent_path.name}: fleet={fm['fleet']!r} not in {sorted(VALID_FLEETS)}"
        )

    def test_model_tier_present_and_valid(self, agent_path: Path) -> None:
        fm = _load_frontmatter(agent_path)
        assert "model_tier" in fm, f"{agent_path.name}: missing `model_tier`"
        assert fm["model_tier"] in VALID_MODEL_TIERS, (
            f"{agent_path.name}: model_tier={fm['model_tier']!r} "
            f"not in {sorted(VALID_MODEL_TIERS)}"
        )
