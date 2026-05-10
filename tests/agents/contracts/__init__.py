"""Pydantic v2 contract models for the Discovery-fleet agents.

T-G3a — these models mirror each agent's *output* contract as documented
in `agents/<name>.md`. Tests under `tests/agents/test_<agent>.py` invoke
deterministic parser shims, then validate the artefacts against these
models. No LLM calls.
"""
