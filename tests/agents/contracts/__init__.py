"""Pydantic v2 contracts for the Operate-fleet agents.

These models are the *contract* the offline tests assert against (per R.T.02 —
test the contract, not the code path). The shim/validator helpers alongside
each model translate fixture-shaped dicts into typed contracts so we can
exercise behaviour without booting the live agents.
"""
