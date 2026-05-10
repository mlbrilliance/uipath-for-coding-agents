"""Pydantic v2 contracts asserted by the agent functional tests (Workstream G).

Each agent's definition under `agents/<name>.md` promises a structured
output artefact. The modules here encode those shapes so the tests under
`tests/agents/test_<agent>.py` can validate recorded fixtures via offline
parser shims — no LLM calls (R.T.02, R.T.03).

Coverage spans every fleet:

- Discovery (T-G3a): scout, curator, analyst, interviewer, strategist.
- Build (T-G3b): architect, cartographer, four forgers, reviewer, tester.
- Operate (T-G3c): sentry, diagnostician, surgeon, auditor, concierge.
- Meta (T-G3d): conductor.
"""
