"""Tester TestPackage contract.

Per `agents/tester.md`, Tester does not call Test Manager directly —
the documented Studio→Orchestrator→Test Manager Select-Automation
linkage owns that hop (T-E1). What Tester *does* emit is a manifest
describing the published package: the `.nupkg` it built, the
Orchestrator package id, and (when the Test Manager link has been
configured) the URL the human reviewer can click into.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class TestPackage(BaseModel):
    """Tester's published-package manifest."""

    __test__ = False  # don't let pytest collect this pydantic model

    model_config = ConfigDict(extra="forbid")

    nupkg_path: Annotated[str, Field(pattern=r".+\.nupkg$")]
    orchestrator_pkg_id: Annotated[str, Field(min_length=1)]
    test_manager_link: HttpUrl | None = None
    coverage: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    tests_total: Annotated[int, Field(ge=0)] = 0
    tests_green: Annotated[int, Field(ge=0)] = 0
