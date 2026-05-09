"""Cartographer references.json contract.

Encodes the selector-reference shape Cartographer emits for Forgers.
Selectors are the Object Repository's contract with the rest of the
swarm, so the validator enforces the strict-find rule (R.SE.01) and the
fallback requirement (R.SE.03).
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Selector(BaseModel):
    """A single selector entry.

    Two non-negotiables:
        R.SE.01 — strict (single-find) only.
        R.SE.03 — at least one fallback using a different stable attribute.
    """

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1)]
    primary: Annotated[str, Field(min_length=1)]
    fallbacks: Annotated[list[str], Field(min_length=1)]
    strict: bool

    @field_validator("strict")
    @classmethod
    def _strict_must_be_true(cls, value: bool) -> bool:
        if not value:
            raise ValueError("R.SE.01: every selector must be strict (single-find)")
        return value


class ReferencesFile(BaseModel):
    """`references.json` shape — flat list keyed by app."""

    model_config = ConfigDict(extra="forbid")

    app: Annotated[str, Field(min_length=1)]
    selectors: Annotated[list[Selector], Field(min_length=1)]
