# AURORA — Autonomous UiPath RPA Operations & Reasoning Agency

**Submission category**: UiPath for Coding Agents
**Demo video**: `<link to be added — the 12-minute walkthrough in docs/demo-script.md>`
**Repo**: https://github.com/mlbrilliance/uipath-for-coding-agents
**Author**: Nick (puneetsatyawan@gmail.com)

---

## TL;DR

A 19-agent coding-agent swarm that doesn't just *build* a UiPath automation — it runs an entire RPA Center of Excellence end-to-end. From a Slack message to a deployed Maestro process to a self-healed production failure to a nightly proposed update of the swarm's own skills, with the human approving exactly two things along the way.

The demo target is **OSS Supply-Chain Defender**: a Maestro-orchestrated agentic process that monitors a GitHub organization's dependency lockfiles against NVD, OSV, and the GitHub Advisory Database, triages findings against a DMN severity matrix, and ships patches with HITL gates on production-affecting fixes. Every UiPath actor type collaborates: RPA bots (XAML), Coded Workflows (C#), Coded Agents (Python LangGraph + OpenAI Agents SDK), DMN decisions, and humans in Action Center. Every BPMN construct that matters is exercised: timer-start, parallel + exclusive gateways, business-rule task, user task with boundary timer, send/receive tasks, sub-process.

100% public data sources. Built on the official `uipath-python` SDK, `UiPath/skills` skill catalogue, and `uipath` CLI. Inference via Claude subscription OAuth — no API key.

---

## What I built

`uipath-for-coding-agents` is an installable Claude Code plugin (also Codex / Cursor compatible) that boots a long-running swarm:

```
                   policy.yaml                   ┌── Discovery loop ──┐
                       │                         │  scout             │
                       ▼                         │  curator           │
   ┌──────────── Conductor ──────────────┐       │  analyst           │
   │  schedules, balances, gates, composts│ ───▶  │  interviewer       │
   └──────────────────┬──────────────────┘       │  strategist        │
                      │                          └────────────────────┘
                      ▼
              ┌── Build loop ───┐               ┌── Operate loop ────┐
              │  architect       │               │  sentry            │
              │  cartographer    │               │  diagnostician     │
              │  forger-rpa      │ ◀───────────▶ │  surgeon           │
              │  forger-coded    │               │  auditor           │
              │  forger-agent    │               │  concierge         │
              │  forger-maestro  │               └────────────────────┘
              │  reviewer        │
              │  tester          │
              └─────────────────┘
```

**The three concurrent loops never pause for each other.** While Build is shipping a new bot, Operate is healing a previously-shipped one, and Discovery is scoring tomorrow's candidates from a configured Slack channel.

Built on:
- `uipath` CLI (installed from `uipath-python`).
- `UiPath/uipath-python` SDK (every Orchestrator interaction goes through it).
- `UiPath/skills` — the seven official skills, all installed: `uipath-rpa-workflows`, `uipath-coded-workflows`, `uipath-coded-agents`, `uipath-flow`, `uipath-platform`, `uipath-coded-apps`, `uipath-servo`.
- Custom: 10 AURORA skills, 19 subagent definitions, 4 hooks, 5 slash-commands, 1 MCP server.

---

## Why it's interesting (Innovation — 40%)

Two patterns in this submission don't exist anywhere else in the public UiPath ecosystem.

### 1. Three concurrent fleets, not phases

Every other coding-agent demo for UiPath I've seen treats the lifecycle as Build → Run → Done. AURORA treats it as Discovery + Build + Operate, all live at once. That's the actual shape of an RPA Center of Excellence: someone is always pitching a new automation; someone is always shipping; someone is always paged at 3am for a broken selector. Modeling it as concurrent loops with explicit handoffs and shared state is the architectural insight.

### 2. Self-evolving skills via the nightly compost step

Every agent writes one-line learnings as it works. Most are mundane. Some recur — the same fingerprint cluster gets the same remediation, three times across two projects, with consistent rationale. The Conductor's nightly compost step:

1. Reads `${AURORA_HOME}/learnings/<date>.jsonl`.
2. Filters for ≥ 3 occurrences across ≥ 2 projects with consistent rationale.
3. Opens a real GitHub PR via `gh pr create --draft` against the swarm's own `skills/<name>/SKILL.md` files.
4. Routes through Action Center for HITL review — **never auto-merge** (R.G.05 in `.claude/rules/aurora-conventions.md`).

The result: AURORA's own skills get measurably better with use, and every change is human-reviewed and version-controlled.

### Plus three smaller novelties

- **Policy-as-code**: the user writes `policy.yaml`, not prompts. Risk gates, model routing, scoring weights, fleet enable/disable — all declarative. Schema-validated. CI-friendly. Live-probed via `aurora policy validate --strict --live` (Orchestrator + GitHub + Action Center catalog reachability).
- **Dual-tier auth via subscription OAuth**: no `ANTHROPIC_API_KEY`. Both Claude Code subagents and the Claude Agent SDK daemons read `~/.claude/credentials.json`. The `.claude/settings.json` even adds a deny-rule on `anthropic.com/v1/messages` to enforce this — any attempt at direct API access fails loudly.
- **Federated worktrees**: the Forger sub-fleet builds in parallel git worktrees under `${AURORA_WORKTREE_DIR}/<job-id>/`, isolated, mergeable. Conductor caps concurrency per `policy.yaml::worktree_pool.max_concurrent`.

---

## Why it's enterprise-relevant (Enterprise Relevance — 30%)

Every agent role maps 1:1 to a real CoE function. CTOs see their org chart:

| AURORA role | Real-world equivalent |
|---|---|
| Scout, Curator, Analyst | Process intelligence + business analysts |
| Architect | Solution architect |
| Cartographer | UI / selector specialist |
| Forger sub-fleet | Senior RPA developer + Python backend dev |
| Reviewer | Peer review, REFramework discipline gatekeeper |
| Tester | QA engineer |
| Sentry, Diagnostician, Surgeon | SRE on-call rotation |
| Auditor | Governance / compliance / FinOps |
| Concierge | ITSM / ServiceNow integrator |
| Strategist | RPA program manager |
| Conductor | CoE lead |

The Defender use case itself is one CTOs lose sleep over. Log4Shell was 2021. The xz-utils backdoor was 2024. **Every enterprise has unowned supply-chain risk** in their public-facing repos. AURORA's Defender process is a working example of automated detection, triage, gated remediation, and continuous improvement — at the maturity level of a real security team.

The migration angle is the second use case. The same swarm could take a 5-year-old REFramework project and modernize it: convert hardcoded values to `Config.xlsx`, wrap external calls in Try/Catch + RetryScope, swap brittle selectors for Object Repository, generate Test Manager test suites, and republish — exactly the example UiPath called out in the original *coding agents are ready for RPA* post.

---

## Demo completeness (Integration Quality & Demo Completeness — 30%)

The 12-minute demo (`docs/demo-script.md`) covers the full lifecycle, end-to-end, in a single take, with three concurrent timelines visible:

| Min | What you see |
|---|---|
| 0:00 | `aurora start` — swarm boots; 19 agents online; cron registry shows three nightly jobs |
| 1:00 | Slack fixture message → Scout → Curator → Analyst |
| 2:00 | Interviewer asks 4 questions in Action Center; I answer |
| 3:00 | Architect picks Maestro; ADR; Forger sub-fleet starts in parallel worktrees |
| 5:00 | BPMN streams into Studio Web canvas; Reviewer comments; Tester writes 12 cases and links them via the Test Manager Select-Automation flow (T-E1) |
| 6:30 | Local validation green; publish to dev via `MaestroService.publish_maestro_project` (T-D3); auto-promote to test |
| 7:00 | **HITL gate #1**: production publish — I approve in Action Center |
| 8:00 | Maestro instance runs; critical finding; Critical sub-process; **HITL gate #2**: emergency patch — I approve; PR opens via `OpenPatchPR` Coded Workflow; CI green; the FastAPI webhook (T-D1) sends the correlation message to Maestro; auto-merge per DMN |
| 9:00 | `./break.sh` injects a failure (invalid `GITHUB_TOKEN`); Sentry catches; Diagnostician fingerprints `auth-failed/token-expired`; Surgeon rotates to `GITHUB_TOKEN_FALLBACK`; Maestro instance resumes; goes green — **no human input** |
| 10:30 | Strategist proposes consolidation; Auditor's cross-folder check passes; HITL approve |
| 11:30 | Nightly compost step proposes a skill update; PR opens; **HITL — but I review and merge on stage** |
| 12:00 | Summary: 1 build, 1 patch, 1 self-heal, 1 consolidation, 1 skill upgrade — **2 human approvals total** |

Every step is real. Real Orchestrator API calls. Real GitHub PRs (Octokit-based, idempotent on duplicate runs). Real Action Center forms. Real BPMN with DMN. The break/heal moment uses a real credential rotation, not a faked retry.

---

## Final-mile changes (resolved decisions D1-D7)

The submission's PDD ran a `grill-with-docs` pass against UiPath's documentation and surfaced seven decisions where the initial design didn't quite match what the platform actually supports. Each is now resolved and shipped:

| ID | Decision | Where it lives |
|---|---|---|
| **D1** | BPMN `<uipath:taskBinding>` is not a documented Studio Web extension. Strip inline; `bindings.json` is the single source of truth. | `examples/oss-supply-chain-defender/bindings.json` + `tests/lint/test_bpmn_no_inline_taskbinding.py` |
| **D2** | Maestro's Receive Task is not executable per [docs.uipath.com/maestro/.../tasks-in-bpmn-modeling](https://docs.uipath.com/maestro/automation-cloud/latest/user-guide/tasks-in-bpmn-modeling). Reshape `WaitForCI` to Send Task → intermediate message catch event (correlation key `pr_url`) → boundary timer (`PT4H`). Fallback (User Task auto-completed by webhook) parked on `feature/waitforci-usertask-fallback`. | `examples/.../process.bpmn`, `tests/lint/test_waitforci_shape.py` (T-D2) |
| **D3** | No documented public CLI verb publishes a Studio Web Maestro project. Built an HTTP wrapper `MaestroService.publish_maestro_project` from a captured Studio Web request shape, plus a Playwright UI fallback. | `lib/aurora/uipath_client.py`, `lib/aurora/playwright/{capture,publish_ui_fallback}.py`, `docs/maestro-publish-bridge.md` (T-D3) |
| **D4** | Live tenant + GitHub demo org provisioned. | `.env` on the VPS; `aurora policy validate --strict --live` probes confirm |
| **D5** | Webhook host: FastAPI on this VPS exposed via Cloudflare Tunnel. HMAC-verified `POST /github/check-run` decodes the GitHub `check_run.completed` event and sends the correlation message to the right Maestro instance. | `webhook/github-check-run/`, `docs/webhook-deploy.md` (T-D1) |
| **D6** | License source: ClearlyDefined.io primary + GitHub Licenses API fallback. | `examples/.../workflows/License/CheckLicenseDrift.xaml` (T-C8) |
| **D7** | Compost-step PR target: this repo, against `skills/<name>/SKILL.md`. Concrete, reviewable, demonstrable. | `lib/aurora/compost.py` |

Plus two doc-corrections that fell out of the same grill pass:
- The CLI is `uipath`, not `uip`. Renamed across skills/docs/scripts (T-A1, regression-tested by `tests/lint/test_no_fictional_uip_cli.py`).
- The Tester agent **links** test cases to Test Manager (Select-Automation flow), it does not **publish** them — Test Manager has no documented write-publish API. Tester's prompt body and the new `lib/aurora/test_manager.py` reflect the corrected flow (T-E1).

---

## Bonus criteria — all four

✅ **Multi-step reasoning end-to-end.** Build → Run → Debug → Fix → Deploy → Monitor → Heal → Govern → Self-improve. All in one take. Validated end-to-end by `tests/agents/test_conductor.py` (4 cross-fleet routing invariants).

✅ **Multi-agent setups with clear roles.** 19 agents in 3 fleets + 1 Conductor. Each with a one-line role definition, scoped tool access, and explicit handoff rules. Agents communicate through the Conductor and shared memory; never direct cross-fleet calls. Asserted by `tests/agents/test_conductor.py::Invariant 1`.

✅ **HITL on risky steps.** Five gates declared in `policy.yaml::gates`: prod_publish, emergency_patch, deprecation, large_fix, skill_compost_pr. Every gate routes through Concierge to Action Center catalog `aurora_supply_chain_approvals`. Asserted by `tests/agents/test_conductor.py::Invariant 2` against the live policy.

✅ **Skills mastery.** Uses all 7 official UiPath skills. Extends the catalog with 10 custom AURORA skills. Reviewer-driven prompt-body lint (`tests/agents/test_all_agents_lint.py`, T-G4) enforces R.SW.06.1 — Build-fleet agents must reference the canonical UiPath skill catalogue.

---

## Try it yourself

```bash
# 1. Install
git clone https://github.com/mlbrilliance/uipath-for-coding-agents.git
cd uipath-for-coding-agents
cp .env.example .env  # fill in UIPATH_*, GITHUB_*, AURORA_*

# 2. Authenticate
claude login                                   # subscription OAuth
ln -s CLAUDE.md AGENTS.md                      # for Codex/Cursor compat

# 3. Install deps
uv sync
uipath skills install                            # interactive — pick all 7

# 4. Install AURORA itself as a Claude Code plugin
claude plugin marketplace add ./
claude plugin install aurora@aurora-marketplace

# 5. Boot
aurora policy validate --strict --live           # pre-flight live probes
aurora start
```

Then open `aurora status` in another terminal, post a friction signal in your configured Discovery source, and watch the swarm.

For a CI-only smoke (no live tenant required):

```bash
aurora start --skip-daemons   # boot policy + cron registry; skip the token mint
make ci                       # lint + typecheck + 515 tests + policy-strict
```

---

## What broke or surprised me

- **`uipath-python` SDK 2.10's folder context is header-based, not URL-based.** Setting `X-UIPATH-OrganizationUnitId` per request was cleaner than threading folder IDs through every call. AURORA's `UiPathClient.folder_context()` context manager handles this.
- **Fingerprint clustering needs canonical kinds upfront.** I tried letting agents invent kinds on the fly. Result: chaos — `auth-error`, `auth-failed`, `auth-fail`, `unauthorised` all became distinct clusters. Fixed by canonicalizing 8 kinds in `lib/aurora/fingerprint.py::CANONICAL_KINDS` and routing anything else through `kind: novel-fault` (which the Conductor escalates).
- **The compost step is the design's keystone.** I started without it and the swarm felt static. Adding it — even with the simplest possible "≥ 3 occurrences across ≥ 2 projects" rule — turned the system into something that actually evolves.
- **Hooks have to be `+x` AND have correct JSON-path parsing.** The biggest silent-degradation bug in the build: the project's `.claude/settings.json` registered four hooks (PreToolUse, PostToolUse, UserPromptSubmit, Notification) but the scripts under `hooks/` had lost their executable bit between commits, so every Claude Code tool call returned `permission denied` and the swarm's memory + fingerprint pipeline was a no-op for the entire history of the project. The triage in commits `d2edb4e`, `43182d6`, `26c80b1` fixed the +x bit, the `/opt/aurora` write-permission default, the brittle `[[ -x ]]` gate in the hooks (now `-f` since they invoke via `python3 <path>`), and the JQ paths (now matching Claude Code's real PostToolUse event schema). New regression test `tests/lint/test_hooks_executable_and_clean.py` smoke-runs every hook in a stripped env to catch this from ever happening again.
- **Not every backend code path is +x.** Same root cause as above caught the four skill scripts (`recall.py`, `cluster.py`, `validate_policy.py`, `mint_token.py`) shipping without +x since the initial commit. Now restored + asserted.

---

## Custom skills, system prompt tweaks, agent-specific config

All written for AURORA, all open-source under MIT.

| Skill | Lines | Has script? | Templates? |
|---|---|---|---|
| `aurora-auth` | 60 | ✅ `mint_token.py` | — |
| `aurora-discover` | 65 | — | — |
| `aurora-pdd` | 75 | — | ✅ `pdd.md`, `ambiguity-rubric.md` |
| `aurora-fingerprint` | 95 | ✅ `cluster.py` | — |
| `aurora-replay` | 60 | ✅ `lib/aurora/replay.py` (T-B1) | — |
| `aurora-promote` | 95 | ✅ `lib/aurora/promote.py` | ✅ 3 form JSONs |
| `aurora-recall` | 70 | ✅ `recall.py` | — |
| `aurora-compost` | 90 | ✅ `lib/aurora/compost.py` (T-B3) | — |
| `aurora-policy` | 85 | ✅ `validate_policy.py` + `lib/aurora/policy_live.py` (T-F2) | — |
| `aurora-deprecate` | 70 | ✅ `lib/aurora/deprecate.py` | — |

System prompt tweaks: `.claude/rules/aurora-conventions.md` injects 60+ rules (UiPath REFramework discipline, AURORA-specific conventions, REFramework structure rules) before every tool call.

Test inventory:
- **515 unit / lint / agents / workflow tests** in `tests/` (`make ci` runs all of these).
- **6 xUnit suites** under `tests/coded/` for the C# Coded Workflows (Notify, OpenAutoPR, OpenPatchPR, PostPendingComment, ResolveLockfiles, Typosquat).
- **6 integration tests** gated by `UIPATH_INTEGRATION=1` for live-tenant verification.

---

## Verifiable claims

Every load-bearing claim in this post maps to a test path that `make ci` runs (or a documented integration test for live-tenant claims). The mapping lives in `docs/submission-claims.json` and is enforced by `tests/docs/test_submission_claims.py`. If a claim ever drifts from its evidence, CI breaks.

---

## License

MIT. PRs welcome.

## Acknowledgments

- **UiPath product team** for `UiPath/skills`, the `uipath` CLI, and the `uipath-python` SDK.
- **@alexandru** and **@Simona_Boboc** for shaping this challenge.
- Pattern inspirations (no code reused, only ideas): Obra Superpowers, Matt Pocock skills, Ouroboros, Factory.ai Missions.
- The community feedback that turned my early "just one more bot" prototype into a swarm.
