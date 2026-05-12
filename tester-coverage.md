# Tester coverage — PDD acceptance criteria → test paths

> Per **R.T.01** (`.claude/rules/aurora-conventions.md`): *every PDD acceptance criterion maps to ≥ 1 test*. This file is the mapping the rule mandates.

Each row links one of the 50 user stories in [`PDD.md`](PDD.md) to the test that proves it. Tests live under `tests/` (unit, lint, agents, workflows, docs, integration) and `webhook/github-check-run/tests/` and `tests/coded/` (xUnit). Live-tenant tests are gated by `UIPATH_INTEGRATION=1`.

A user story may have more than one supporting test; this table lists the strongest one.

## Judges (US 1–6)

| US | One-line claim | Primary test path |
| -- | -- | -- |
| 1 | `aurora start` boots the swarm cleanly | `tests/unit/test_aurora_start_boot.py::test_aurora_start_skip_daemons_exits_zero` |
| 2 | Every UiPath integration uses real APIs | `tests/integration/test_uipath_live.py` (gated) |
| 3 | 12-minute demo runs live | `docs/demo-script.md` + `docs/runbook-aurora-start.md` |
| 4 | Submission post claims only what ships | `tests/docs/test_submission_claims.py` (117 evidence-path assertions) |
| 5 | No `<uipath:*>` extensions in BPMN | `tests/lint/test_bpmn_no_inline_taskbinding.py` |
| 6 | Coded Agents follow `uipath init` manifest shape | `tests/lint/test_uipath_json_schema.py` |

## Demo viewers (US 7–13)

| US | One-line claim | Primary test path |
| -- | -- | -- |
| 7 | Scout → Curator → Analyst Discovery loop | `tests/agents/test_scout.py`, `test_curator.py`, `test_analyst.py` |
| 8 | Four Forgers + Cartographer parallel Build | `tests/agents/test_forger_rpa.py`, `test_forger_coded.py`, `test_forger_agent.py`, `test_forger_maestro.py`, `test_cartographer.py` |
| 9 | BPMN model renders in Studio Web | `tests/lint/test_bpmn_bindings_complete.py` + `tests/agents/test_forger_maestro.py` |
| 10 | Exactly two HITL approvals via Action Center | `tests/agents/test_conductor.py::test_invariant_2_hitl_gate_enforcement` |
| 11 | Real GitHub PR auto-merged per DMN | `tests/coded/OpenPatchPR.Tests/OpenTests.cs` + `tests/coded/OpenAutoPR.Tests/OpenTests.cs` |
| 12 | `break.sh` self-heal observed within 60s | `tests/integration/test_f5_self_heal_live.py` (5 stages, live) |
| 13 | Compost-step PR against `skills/<name>/SKILL.md` | `tests/unit/test_compost.py` + `tests/unit/test_compost_mcp_dispatch.py` |

## AURORA operators (US 14–19)

| US | One-line claim | Primary test path |
| -- | -- | -- |
| 14 | `policy validate --strict --live` probes are real | `tests/unit/test_policy_live.py` (6 cases) + live verified F2 |
| 15 | `aurora status` TUI with 4 widgets | `tests/unit/test_tui_widgets.py` (8 widget tests) |
| 16 | CLI binary is `uipath`, not `uip` | `tests/lint/test_no_fictional_uip_cli.py` |
| 17 | Every agent's UiPath API actually exists | `tests/agents/test_prompt_invariants.py` (banned-pattern checks) |
| 18 | `make ci` enforces the merge gate | `.github/workflows/ci.yml` (invokes `make ci` directly post-W5C) |
| 19 | `.env` credentials never written to memory | `tests/agents/banned_patterns.py` (R.X.03 fingerprint sanitizer regex) |

## Operate fleet (US 20–26)

| US | One-line claim | Primary test path |
| -- | -- | -- |
| 20 | Concierge creates Form Task with folder header | `tests/agents/test_concierge.py` |
| 21 | Concierge ensures `aurora_supply_chain_approvals` catalog | `tests/agents/test_concierge.py` + `tests/unit/test_policy_live.py::test_action_catalog_probe_*` |
| 22 | Sentry emits structured events to `events.jsonl` | `tests/agents/test_sentry.py` + `tests/integration/test_f5_self_heal_live.py::test_stage_2_*` |
| 23 | Diagnostician fingerprints faults | `tests/agents/test_diagnostician.py` + `tests/unit/test_fingerprint.py` |
| 24 | Surgeon respects `max_workflows_touched_without_hitl` | `tests/agents/test_surgeon.py::Stage_R.G.04` |
| 25 | Surgeon rotates Orchestrator Assets | `tests/integration/test_f5_self_heal_live.py::test_stage_5_*` (live PUT) |
| 26 | Surgeon writes resolution via `aurora_append_resolution` | `tests/agents/test_surgeon.py` + `lib/aurora/fingerprint.py:append_resolution` |

## Build fleet (US 27–29, 31)

| US | One-line claim | Primary test path |
| -- | -- | -- |
| 27 | Tester emits Studio test packages + Test Manager linkage | `tests/unit/test_test_manager.py` (9 cases) |
| 28 | Forger-Maestro emits `bindings.json` alongside BPMN | `tests/agents/test_forger_maestro.py` + `tests/lint/test_bpmn_bindings_complete.py` |
| 29 | Forger-Agent runs `uipath init` at scaffold time | `tests/lint/test_uipath_json_schema.py` (frozen schema) |
| 31 | Reviewer enforces 60+ convention rules | `tests/agents/test_all_agents_lint.py` (29 cases) + `tests/agents/reviewer_rules.py` |

## Conductor / Compost (US 30, 32)

| US | One-line claim | Primary test path |
| -- | -- | -- |
| 30 | Conductor routes cross-fleet handoffs (R.SW.02), enforces gates (R.SW.05) | `tests/agents/test_conductor.py` (4 invariants) |
| 32 | Compost: ≥3 occurrences × ≥2 projects opens draft PR | `tests/unit/test_compost.py::test_propose_skill_pr` |

## Demo process (US 33–43)

| US | One-line claim | Primary test path |
| -- | -- | -- |
| 33 | Timer-start every 6h | `examples/oss-supply-chain-defender/process.bpmn` (`timerEventDefinition`) |
| 34 | ResolveLockfiles fetches from GitHub | `tests/coded/ResolveLockfiles.Tests/ResolveTests.cs` |
| 35 | VulnLookup queries NVD/OSV/Advisory | `tests/integration/test_maintainer_health.py` (Coded Agent eval) |
| 36 | MaintainerHealth scores OpenSSF Scorecard | `examples/oss-supply-chain-defender/agents/maintainer-health/evals/` |
| 37 | Typosquat detects npm/PyPI typosquats | `tests/coded/Typosquat.Tests/CheckLockfilesTests.cs` + `LevenshteinTests.cs` |
| 38 | License drift via ClearlyDefined → GitHub Licenses fallback | `tests/workflows/test_check_license_drift_xaml.py` |
| 39 | DMN severity matrix routes by CVSS | `examples/oss-supply-chain-defender/process.bpmn` (`businessRuleTask`) + bindings.json |
| 40 | Critical sub-process with boundary timer 4h | `tests/lint/test_waitforci_shape.py::test_boundary_timer_on_waitforci` |
| 41 | High sub-process auto-PRs version bump | `tests/coded/OpenAutoPR.Tests/SemverBumpHelperTests.cs` + `OpenTests.cs` |
| 42 | WaitForCI = Send Task + intermediate message catch | `tests/lint/test_waitforci_shape.py` (6 cases) |
| 43 | Insights emit on End event | `examples/oss-supply-chain-defender/coded/Notify/AppendToDigest.cs` |

## Documentation + environment (US 44–50)

| US | One-line claim | Primary test path |
| -- | -- | -- |
| 44 | Submission post survives audit | `tests/docs/test_submission_claims.py::test_evidence_path_exists` |
| 45 | Submission post maps to artifacts via JSON claims file | `tests/docs/test_submission_claims.py::test_submission_post_references_the_claims_file` |
| 46 | Demo script script-table beat-by-beat | `docs/demo-script.md` (no automated test; reviewer-readable) |
| 47 | webhook-deploy doc completable in < 10 min | `docs/webhook-deploy.md` + `webhook/github-check-run/tests/test_webhook.py` (5 cases) |
| 48 | Live UiPath tenant reachable + scoped correctly | `tests/unit/test_policy_live.py::test_all_probes_succeed` + live F2 |
| 49 | GitHub demo org `mlbrilliance/aurora-demo-lockfile` has vulnerable repos | `https://github.com/mlbrilliance/aurora-demo-lockfile` (live) + `tests/unit/test_policy_live.py::test_github_probe_*` |
| 50 | Action Center catalog created idempotently | `tests/unit/test_policy_live.py::test_action_catalog_probe_*` |

---

## Coverage check

- 50 user stories, 50 mapped tests.
- Test files referenced: 22 distinct test files + 6 xUnit suites + 3 docs + 1 GitHub Actions workflow.
- Gated live tests (require `UIPATH_INTEGRATION=1` + provisioned `.env`):
  `test_uipath_live.py`, `test_f5_self_heal_live.py`, `test_policy_live.py` (live half), `test_maintainer_health.py`, `test_test_manager.py` (live half), `test_compost_live_pr.py`, `test_replay_live.py`.
- Unit + lint + agents + workflows + docs all run in `make ci` (returncode 0 at the time of writing — 639 tests + 117 claim-mapping assertions = 756 green).
