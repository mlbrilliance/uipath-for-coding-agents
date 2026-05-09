"""T-G3b — Reviewer contract test.

Two fixtures:
    - `clean_xaml.xml`     → LintResult.errors == []
    - `violation_xaml.xml` → ≥ 1 error citing R.X.01 (String password)

The shim is a tiny linter that scans for the R.X.01 violation pattern
recorded in `agents/reviewer.md` (item 5 of the cross-cutting checks).

Satisfies US-9, US-31.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.agents.contracts.reviewer import LintFinding, LintResult, Severity

FIXTURES = Path(__file__).parent / "fixtures" / "reviewer"

PASSWORD_AS_STRING_RE = re.compile(
    r'Name="(?P<name>in_strPassword|in_strPwd|in_strPass)"\s+Type="InArgument\(x:String\)"'
)


def _lint(path: Path) -> LintResult:
    text = path.read_text(encoding="utf-8")
    errors: list[LintFinding] = []
    for match in PASSWORD_AS_STRING_RE.finditer(text):
        errors.append(
            LintFinding(
                severity=Severity.ERROR,
                rule="R.X.01",
                path=str(path),
                message=(
                    f"Argument {match.group('name')!r} declared as String; "
                    "credentials must be SecureString."
                ),
            )
        )
    return LintResult(errors=errors)


def test_clean_xaml_has_no_errors() -> None:
    result = _lint(FIXTURES / "clean_xaml.xml")
    assert result.is_clean, f"clean fixture must lint clean; got {result.errors}"
    assert result.errors == []


def test_violation_xaml_flags_string_password() -> None:
    result = _lint(FIXTURES / "violation_xaml.xml")
    assert not result.is_clean, "violation fixture must produce at least one error"
    assert len(result.errors) >= 1
    rules = {e.rule for e in result.errors}
    assert "R.X.01" in rules, f"expected R.X.01 in {rules}"


def test_lint_finding_rule_format_is_validated() -> None:
    """Rule ids follow the `R.<CAT>.<NN>` shape — bad strings are rejected."""
    import pytest

    with pytest.raises(ValueError):
        LintFinding(
            severity=Severity.ERROR,
            rule="not-a-rule",
            path="x.xaml",
            message="m",
        )
