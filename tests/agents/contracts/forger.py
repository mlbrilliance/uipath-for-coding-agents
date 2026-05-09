"""Shared Forger artefact contract.

All four Forger sub-specialists (`forger-rpa`, `forger-coded`,
`forger-agent`, `forger-maestro`) ultimately emit a list of file paths
into a worktree. The shape is identical; what differs is the validator
that walks each path and asserts file-level discipline.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

ARG_PREFIX_RE = re.compile(r"\b(in_|out_|io_)[A-Za-z]")


class ForgerArtifact(BaseModel):
    """The structured artefact every Forger reports up to Conductor."""

    model_config = ConfigDict(extra="forbid")

    forger: Annotated[str, Field(min_length=1)]
    candidate_id: Annotated[str, Field(min_length=1)]
    emitted_paths: Annotated[list[Path], Field(min_length=1)]


def has_arg_prefix(text: str) -> bool:
    """R.N.02: at least one argument with a direction prefix is present."""
    return ARG_PREFIX_RE.search(text) is not None


def assert_namespace(text: str) -> str:
    """R.N.04: namespace must be `<Solution>.<Module>.<Action>` PascalCase.

    Returns the matched namespace for downstream assertions; raises
    `AssertionError` if no compliant namespace is found.
    """
    match = re.search(r"namespace\s+([A-Za-z][A-Za-z0-9_.]*)", text)
    assert match, "R.N.04: no `namespace` declaration found"
    parts = match.group(1).split(".")
    assert len(parts) >= 3, (
        f"R.N.04: namespace `{match.group(1)}` must be `<Solution>.<Module>.<Action>`; "
        f"got {len(parts)} segment(s)"
    )
    for part in parts:
        assert part[:1].isupper() and part.isidentifier(), (
            f"R.N.04: namespace segment `{part}` must be PascalCase"
        )
    return match.group(1)
