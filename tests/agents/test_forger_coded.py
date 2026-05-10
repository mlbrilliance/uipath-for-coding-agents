"""T-G3b — Forger-Coded contract test.

Reads a sample C# coded workflow and asserts it satisfies the
disciplines in `agents/forger-coded.md`:

    R.N.04 — namespace pattern `<Solution>.<Module>.<Action>`.
    R.K.02 — no `async void`; only `async Task<T>`.
    R.L.03 — `Log.Information(...)`, never `print()` / `Console.WriteLine`.

Satisfies US-9, US-31.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.agents.contracts.forger import ForgerArtifact, assert_namespace

FIXTURE = Path(__file__).parent / "fixtures" / "forger_coded" / "sample_workflow.cs"


def _read() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_artifact_shape() -> None:
    artifact = ForgerArtifact(
        forger="forger-coded",
        candidate_id="CAND-CODED-001",
        emitted_paths=[FIXTURE],
    )
    assert artifact.emitted_paths[0].suffix == ".cs"


def test_namespace_is_solution_module_action() -> None:
    """R.N.04 — namespace must have ≥ 3 PascalCase segments."""
    namespace = assert_namespace(_read())
    assert namespace.startswith("AuroraSupplyChainDefender."), (
        f"R.N.04: namespace `{namespace}` must start with Solution prefix"
    )


def test_no_async_void() -> None:
    """R.K.02 — `async void` is banned; use `async Task<T>`."""
    text = _read()
    bad = re.search(r"\basync\s+void\b", text)
    assert bad is None, "R.K.02: `async void` is forbidden"


def test_uses_log_information_not_print() -> None:
    """R.L.03 — coded workflows must use `Log.Information`."""
    text = _read()
    assert "Log.Information(" in text, "R.L.03: must use `Log.Information(...)`"
    assert "Console.WriteLine" not in text, "R.L.03: `Console.WriteLine` is forbidden"
    assert re.search(r"\bprint\s*\(", text) is None, "R.L.03: `print()` is forbidden in C# workflows"


def test_assert_namespace_rejects_two_segments() -> None:
    with pytest.raises(AssertionError, match=r"R\.N\.04"):
        assert_namespace("namespace Foo.Bar { }")
