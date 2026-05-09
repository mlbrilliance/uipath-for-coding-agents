"""Pydantic v2 contracts asserted by Build-fleet agent tests.

Each Build agent's definition (under `agents/`) promises a structured
artefact shape. The modules in this package encode those shapes so the
tests under `tests/agents/test_<agent>.py` can validate fixtures
without invoking an LLM (R.T.02, R.T.03).
"""
