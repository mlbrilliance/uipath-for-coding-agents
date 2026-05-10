"""T-G3b — Forger-Agent contract test.

Reads a sample `main.py` and asserts the disciplines in
`agents/forger-agent.md`:

    R.K.04 — prompts referenced via `prompts/*.md`, never inlined.
    R.K.05 — `main()` returns a typed pydantic object.

Satisfies US-9, US-31.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "forger_agent" / "sample_main.py"


def _source() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _module() -> ast.Module:
    return ast.parse(_source())


def test_prompts_loaded_from_files_not_inlined() -> None:
    """R.K.04 — prompts live under prompts/*.md; the module reads them."""
    src = _source()
    assert re.search(r"prompts/\w+\.md", src), (
        "R.K.04: module must reference a prompts/*.md file"
    )
    triple = re.findall(r'(?:"""|\'\'\').{200,}?(?:"""|\'\'\')', src, flags=re.DOTALL)
    long_strings = [s for s in triple if "prompt" in s.lower() or "you are" in s.lower()]
    assert not long_strings, (
        "R.K.04: long prompt-like triple-quoted strings detected — move to prompts/*.md"
    )


def test_main_has_pydantic_return_annotation() -> None:
    """R.K.05 — `main()` returns a typed object (pydantic BaseModel subclass)."""
    module = _module()
    main_def: ast.FunctionDef | None = next(
        (n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == "main"),
        None,
    )
    assert main_def is not None, "module must define `main`"
    assert main_def.returns is not None, "R.K.05: `main()` must declare a return annotation"

    return_name = (
        main_def.returns.id if isinstance(main_def.returns, ast.Name) else ast.unparse(main_def.returns)
    )
    classes = {n.name: n for n in module.body if isinstance(n, ast.ClassDef)}
    assert return_name in classes, (
        f"R.K.05: return type {return_name!r} must be a class defined in this module"
    )

    return_class = classes[return_name]
    base_names = {ast.unparse(b) for b in return_class.bases}
    assert "BaseModel" in base_names, (
        f"R.K.05: {return_name} must subclass pydantic.BaseModel; bases={base_names}"
    )


def test_no_print_statements() -> None:
    """R.L.04 — coded agents use structured logging, never `print()`."""
    module = _module()
    calls = [
        n for n in ast.walk(module)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"
    ]
    assert not calls, "R.L.04: bare `print()` calls are forbidden in coded agents"
