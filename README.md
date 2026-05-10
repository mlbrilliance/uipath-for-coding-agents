# AURORA

### Autonomous UiPath RPA Operations & Reasoning Agency

> **Most submissions to the UiPath for Coding Agents challenge are coding agents that build one bot.
> AURORA is an org chart that runs forever.**

A **19-agent swarm** in three concurrent fleets — Discovery, Build, Operate — coordinated by a
Conductor that schedules, balances, gates, and runs a nightly **compost step** that proposes
upgrades to the swarm's own skills. From a Slack message to a deployed UiPath Maestro process to
a self-healed production failure to a draft skill PR, with **two human approvals total**.

Every UiPath actor type collaborates: RPA bots (XAML), Coded Workflows (C#), Coded Agents
(Python LangGraph + OpenAI Agents SDK), DMN decisions, and humans in Action Center. Every BPMN
construct that matters is exercised: timer-start, parallel + exclusive gateways, business-rule
task, user task with boundary timer, send/receive tasks, sub-process. **Live-verified against a
real UiPath Automation Cloud tenant** — five F5 self-heal stages pass in under 4 seconds.

```
                                          policy.yaml
                                              │
   ┌──────── Discovery ────────┐    ┌─── Conductor ───┐    ┌──────── Operate ──────────┐
   │  scout                    │    │ schedules       │    │  sentry                   │
   │  curator                  │    │ balances        │    │  diagnostician            │
   │  analyst                  │ ◀──┤ gates           ├──▶ │  surgeon                  │
   │  interviewer              │    │ composts        │    │  auditor                  │
   │  strategist               │    └────────┬────────┘    │  concierge                │
   └───────────────────────────┘             │             └───────────────────────────┘
                                             ▼
                                    ┌── Build ─────────┐
                                    │  architect       │
                                    │  cartographer    │
                                    │  forger-rpa      │
                                    │  forger-coded    │
                                    │  forger-agent    │
                                    │  forger-maestro  │
                                    │  reviewer        │
                                    │  tester          │
                                    └──────────────────┘
```

The three loops never pause for each other. While Build is shipping a new bot, Operate is healing
a previously-shipped one, and Discovery is scoring tomorrow's candidates from a configured Slack
channel.

---

## Table of contents

1. [Why this is different](#why-this-is-different)
2. [What's inside](#whats-inside) — every UiPath capability mapped to a real artifact
3. [Live-tenant verification](#live-tenant-verification) — the receipts
4. [Try it in 5 minutes (no tenant)](#try-it-in-5-minutes-no-tenant)
5. [Run it live (with a tenant)](#run-it-live-with-a-tenant)
6. [The 12-minute demo](#the-12-minute-demo)
7. [Architecture deep-dive](#architecture-deep-dive)
8. [Repo geometry](#repo-geometry)
9. [Convention discipline](#convention-discipline) — the 60+ REFramework rules
10. [Configuration](#configuration)
11. [What broke or surprised us](#what-broke-or-surprised-us)
12. [Known limits and future work](#known-limits-and-future-work)
13. [Built on](#built-on)
14. [Contributing](#contributing)
15. [Acknowledgments](#acknowledgments)
16. [License](#license)

---

## Why this is different

### Three pillars

#### 1. Three concurrent fleets, not phases

Every other coding-agent demo for UiPath models the lifecycle as **Build → Run → Done**. AURORA
models it as **Discovery + Build + Operate**, all live at once. That's the actual shape of an
RPA Center of Excellence: someone is always pitching a new automation; someone is always
shipping; someone is always paged at 3am for a broken selector. Modeling it as concurrent loops
with explicit handoffs through a single Conductor and shared memory is the architectural
insight.

#### 2. Self-evolving skills via the nightly compost step

Every agent writes one-line learnings as it works. Most are mundane. Some recur — the same
fingerprint cluster gets the same remediation, three times across two projects, with consistent
rationale. The Conductor's nightly **compost step**:

1. Reads `${AURORA_HOME}/learnings/<date>.jsonl`.
2. Filters for **≥ 3 occurrences across ≥ 2 projects with consistent rationale**.
3. Opens a real `gh pr create --draft` against this repo's `skills/<name>/SKILL.md`.
4. Routes through **Action Center for HITL review** — never auto-merge (R.G.05 in the rules).

The result: AURORA's own skills get measurably better with use, and every change is
human-reviewed and version-controlled.

#### 3. Live-verified

`aurora policy validate --strict --live` proves Orchestrator + GitHub + Action Center catalog
are reachable. `aurora start` runs ≥ 5 minutes against a real UiPath tenant with **zero ERROR
entries**, every Sentry tick a 200 OK against `/odata/Folders`, `/odata/Jobs`,
`/maestro_/api/instances`. **639 unit/lint/agents/workflow tests** in CI. Six xUnit suites for
the C# Coded Workflows. Five live-integration tests for the Surgeon self-heal chain (read +
write through `/odata/Assets`). **No mocks in production paths.**

### Plus three smaller novelties

- **Policy-as-code.** The user writes `policy.yaml`, not prompts. Risk gates, model routing,
  scoring weights, fleet enable/disable — all declarative. JSON-schema-validated. CI-friendly.
  Live-probed.
- **Dual-tier auth via subscription OAuth.** No `ANTHROPIC_API_KEY`. Both Claude Code subagents
  and the Claude Agent SDK daemons read `~/.claude/credentials.json`. The `.claude/settings.json`
  even adds a deny-rule on `anthropic.com/v1/messages` to enforce this — any attempt at direct
  API access fails loudly.
- **Federated worktrees.** The Forger sub-fleet builds in parallel git worktrees under
  `${AURORA_WORKTREE_DIR}/<job-id>/`, isolated, mergeable. The Conductor caps concurrency per
  `policy.yaml::worktree_pool.max_concurrent`. Used heavily during this build itself —
  Workstream G's four parallel droids each ran in their own worktree.

---

## What's inside

Built on the official UiPath surface — every actor type exercised, mapped to a real shipped
artifact:

| UiPath capability                          | AURORA artifact                                                                                                  | xUnit / pytest                                |
| ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **Maestro** (BPMN 2.0 + DMN)               | [`process.bpmn`](examples/oss-supply-chain-defender/process.bpmn) + [`bindings.json`](examples/oss-supply-chain-defender/bindings.json) | `tests/lint/test_bpmn_*.py`, `test_waitforci_shape.py` |
| **RPA workflow** (XAML)                    | [`CheckLicenseDrift.xaml`](examples/oss-supply-chain-defender/workflows/License/CheckLicenseDrift.xaml)          | `tests/workflows/test_check_license_drift_xaml.py` |
| **Coded Workflow (C#)** — 6 of them        | [`Typosquat`](examples/oss-supply-chain-defender/coded/Typosquat/), [`ResolveLockfiles`](examples/oss-supply-chain-defender/coded/ResolveLockfiles/), [`Notify`](examples/oss-supply-chain-defender/coded/Notify/), [`OpenPatchPR`](examples/oss-supply-chain-defender/coded/OpenPatchPR/), [`OpenAutoPR`](examples/oss-supply-chain-defender/coded/OpenAutoPR/), [`PostPendingComment`](examples/oss-supply-chain-defender/coded/PostPendingComment/) | 6 xUnit suites under `tests/coded/`           |
| **Coded Agent (Python)** — 2 of them       | [`maintainer-health`](examples/oss-supply-chain-defender/agents/maintainer-health/) (OpenAI Agents SDK), [`vuln-lookup`](examples/oss-supply-chain-defender/agents/vuln-lookup/) (LangGraph) | `tests/integration/test_maintainer_health.py` |
| **Action Center Form Tasks**               | [`lib/aurora/promote.py`](lib/aurora/promote.py) + [Form templates](skills/aurora-promote/templates/)             | `tests/unit/test_promote.py`                  |
| **Test Manager linkage**                   | [`lib/aurora/test_manager.py`](lib/aurora/test_manager.py) + [Playwright fallback](lib/aurora/playwright/test_manager_ui.py) | `tests/unit/test_test_manager.py`             |
| **Maestro publish bridge**                 | [`uipath_client.publish_maestro_project`](lib/aurora/uipath_client.py) + [Playwright capture/UI](lib/aurora/playwright/) | `tests/unit/test_maestro_publish.py`          |
| **Webhook for `check_run.completed`**      | [`webhook/github-check-run/`](webhook/github-check-run/) — FastAPI, HMAC-verified, dedup LRU                     | `webhook/github-check-run/tests/test_webhook.py` |
| **Orchestrator Asset rotation** (self-heal) | [`uipath_client.update_asset`](lib/aurora/uipath_client.py)                                                      | `tests/integration/test_f5_self_heal_live.py` (live) |

Plus all 7 official UiPath skills (`uipath-rpa-workflows`, `uipath-coded-workflows`,
`uipath-coded-agents`, `uipath-flow`, `uipath-platform`, `uipath-coded-apps`, `uipath-servo`)
and 10 custom AURORA skills:

| Skill                    | Purpose                                                          |
| ------------------------ | ---------------------------------------------------------------- |
| `aurora-auth`            | Mint + refresh UiPath OAuth tokens                               |
| `aurora-discover`        | Extract friction signals from Slack/Jira/email fixtures          |
| `aurora-pdd`             | Author PDDs with ambiguity scoring                               |
| `aurora-fingerprint`     | Cluster fault events by structural pattern                       |
| `aurora-replay`          | Twin-replay a faulted Maestro instance against a sandbox folder  |
| `aurora-promote`         | HITL gate via Action Center Form Task                            |
| `aurora-recall`          | Scoped memory retrieval (project / org / skill tier)             |
| `aurora-compost`         | Nightly: read learnings → propose skill PR                       |
| `aurora-policy`          | Validate policy.yaml; live-probe Orchestrator + GitHub + catalog |
| `aurora-deprecate`       | Process retirement with rollback                                 |

---

## Live-tenant verification

The five integration tests under [`tests/integration/test_f5_self_heal_live.py`](tests/integration/test_f5_self_heal_live.py)
run **end-to-end against a real UiPath Automation Cloud tenant** in under 4 seconds:

| Stage | What it proves                                                                                  | Endpoint                                       | Status   |
| :---: | ----------------------------------------------------------------------------------------------- | ---------------------------------------------- | -------- |
| **2** | Sentry's `_emit_job_fault` writes a `kind=job_failed` event to `events.jsonl`                  | (in-process)                                   | ✓ PASS   |
| **3** | `classify_event()` clusters as `kind=auth-failed`, `refinement=token-expired`                  | (in-process)                                   | ✓ PASS   |
| **3b**| The cluster persists to `fingerprints.db` with `occurrences ≥ 1`                               | (sqlite)                                       | ✓ PASS   |
| **4** | Surgeon's read path against `/odata/Assets` returns 200 with folder-scoped auth                 | `GET /odata/Assets` (folder header)            | ✓ PASS   |
| **5** | Surgeon's full **read → mutate → restore** round-trip against a real Credential asset          | `PUT /odata/Assets({id})`                      | ✓ PASS   |

```bash
$ UIPATH_INTEGRATION=1 .venv/bin/pytest tests/integration/test_f5_self_heal_live.py -v
tests/integration/test_f5_self_heal_live.py::test_stage_2_sentry_emits_job_fault_to_events_jsonl              PASSED [ 20%]
tests/integration/test_f5_self_heal_live.py::test_stage_3_diagnostician_clusters_as_auth_failed_token_expired PASSED [ 40%]
tests/integration/test_f5_self_heal_live.py::test_stage_3b_fingerprints_db_persists_the_cluster              PASSED [ 60%]
tests/integration/test_f5_self_heal_live.py::test_stage_4_surgeon_can_list_assets_against_live_tenant        PASSED [ 80%]
tests/integration/test_f5_self_heal_live.py::test_stage_5_surgeon_round_trips_asset_value_against_live_tenant PASSED [100%]
========================= 5 passed in 3.97s =========================
```

Plus:

- `aurora policy validate --strict --live` → **3/3 probes ok** (Orchestrator, GitHub, Action Center catalog)
- `aurora start` → **5 minutes clean**, 24 successful Sentry ticks, **0 ERROR entries**

---

## Try it in 5 minutes (no tenant)

The CI-only smoke path. Boots the policy + cron registry without touching Orchestrator. Useful
for:

- Verifying you can build the project end-to-end.
- Running `make ci` (lint + typecheck + 639 tests + policy-strict) on your own machine.
- Reading the architecture diagrams in `aurora status` (Textual TUI).

```bash
git clone https://github.com/mlbrilliance/uipath-for-coding-agents.git
cd uipath-for-coding-agents
uv sync                                   # Python deps; takes ~60s
.venv/bin/aurora start --skip-daemons     # boot policy + cron registry; skip token mint
make ci                                   # lint + typecheck + 639 tests + policy-strict
```

Expected:

```
[aurora] loading policy…
[aurora] policy: valid (0 warning(s))
[aurora] --skip-daemons: skipping UiPath token mint
[aurora] --skip-daemons: not starting Operate fleet
[aurora] conductor: ready (in-session mode)
exit 0

make ci returncode=0
639 passed, 2 skipped in 4.27s
```

---

## Run it live (with a tenant)

```bash
# 1. Configure
cp .env.example .env             # fill in UIPATH_*, GITHUB_*, AURORA_*

# 2. Authenticate
claude login                     # subscription OAuth → ~/.claude/credentials.json
ln -s CLAUDE.md AGENTS.md        # for Codex/Cursor compat

# 3. Install UiPath skills (interactive — pick all 7)
uipath skills install

# 4. Pre-flight: 3/3 live probes
aurora policy validate --strict --live

# 5. Boot the swarm
aurora start                     # blocks; daemons run in-process

# 6. In another terminal: the TUI dashboard
aurora status
```

The 5-minute live verification runbook with the exact `grep` recipe to assert no ERROR entries
lives at [`docs/runbook-aurora-start.md`](docs/runbook-aurora-start.md).

For the full demo (Maestro publish + WaitForCI), one extra step: stand up a Cloudflare trial
tunnel for the FastAPI webhook. **No Cloudflare account required** — `cloudflared tunnel --url
http://localhost:8000` prints a `*.trycloudflare.com` URL anonymously. Recipe in
[`docs/webhook-deploy.md`](docs/webhook-deploy.md).

---

## The 12-minute demo

The demo target is **OSS Supply-Chain Defender** — a Maestro process that monitors a GitHub
org's lockfiles against NVD, OSV, and the GitHub Advisory Database, triages findings against a
DMN severity matrix, and ships patches with HITL gates on production-affecting fixes.

The 12-minute walkthrough covers the full lifecycle in one take, with three concurrent timelines
visible.

| Min   | What you see                                                                                                                                                                                           |
| :---: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 0:00  | `aurora start` — swarm boots; 19 agents online; cron registry shows three nightly jobs                                                                                                                 |
| 1:00  | Slack fixture message → Scout → Curator → Analyst                                                                                                                                                      |
| 2:00  | Interviewer asks 4 questions in Action Center; human answers                                                                                                                                            |
| 3:00  | Architect picks Maestro; ADR; Forger sub-fleet starts in parallel worktrees                                                                                                                            |
| 5:00  | BPMN streams into Studio Web canvas; Reviewer comments; Tester writes 12 cases and links them via Test Manager Select-Automation flow                                                                  |
| 6:30  | Local validation green; publish to dev via `MaestroService.publish_maestro_project`; auto-promote to test                                                                                              |
| 7:00  | **HITL gate #1**: production publish — human approves in Action Center                                                                                                                                 |
| 8:00  | Maestro instance runs; critical finding; Critical sub-process; **HITL gate #2**: emergency patch — human approves; PR opens via `OpenPatchPR`; CI green; webhook unblocks Maestro; auto-merge per DMN |
| 9:00  | `./break.sh` injects a failure (invalid `GITHUB_TOKEN`); Sentry catches; Diagnostician fingerprints `auth-failed/token-expired`; Surgeon rotates to `GITHUB_TOKEN_FALLBACK`; instance resumes — **no human input** |
| 10:30 | Strategist proposes consolidation; Auditor's cross-folder check passes; HITL approve                                                                                                                   |
| 11:30 | Nightly compost step proposes a skill update; PR opens; **HITL — human reviews and merges on stage**                                                                                                  |
| 12:00 | Summary: 1 build, 1 patch, 1 self-heal, 1 consolidation, 1 skill upgrade — **2 human approvals total**                                                                                                 |

Every step is real. Real Orchestrator API calls. Real GitHub PRs (Octokit-based, idempotent on
duplicate runs). Real Action Center forms. Real BPMN with DMN. The break/heal moment uses a
real Credential rotation, not a faked retry.

Full beat-by-beat script: [`docs/demo-script.md`](docs/demo-script.md).

---

## Architecture deep-dive

### Discovery (5 agents) — *what should we automate?*

| Agent          | Job                                                                                                              |
| -------------- | ---------------------------------------------------------------------------------------------------------------- |
| `scout`        | Passive sensor. Reads Slack/Jira/email fixtures, surfaces friction signals.                                       |
| `curator`      | Deduplicates, clusters near-duplicates, maintains the candidate backlog.                                          |
| `analyst`      | Authors PDDs, scores ROI = frequency × pain × feasibility.                                                        |
| `interviewer`  | Socratic Q&A when ambiguity > 0.4 (asks ≤ 5 questions via Concierge).                                             |
| `strategist`   | Quarterly retrospective. Proposes consolidation / deprecation / re-prioritization / platform investment.          |

### Build (8 agents) — *idea → running bot*

| Agent             | Job                                                                                                            |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| `architect`       | Picks the UiPath pattern: Sequence / REFramework / Coded Workflow / Coded Agent / Maestro / Action Center / DU. |
| `cartographer`    | Builds the Object Repository via Playwright MCP + `inspect-ui-tree.ps1`. Strict single-find selectors.          |
| `forger-rpa`      | XAML generator using the official `uipath-rpa-workflows` skill.                                                |
| `forger-coded`    | C# coded automation generator using `uipath-coded-workflows`.                                                  |
| `forger-agent`    | Python agent generator using `uipath-coded-agents` (LangGraph / OpenAI Agents / LlamaIndex).                   |
| `forger-maestro`  | Emits BPMN 2.0 + DMN + bindings.json; publishes via `uipath-platform`.                                          |
| `reviewer`        | Enforces the 60+ rules from `.claude/rules/aurora-conventions.md`. Blocks merge on error.                      |
| `tester`          | Writes Test Manager test cases from PDD acceptance criteria; publishes; links via Select-Automation flow.       |

### Operate (5 agents) — *running bots → SLA-met fleet*

| Agent             | Job                                                                                                            |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| `sentry`          | Polls Orchestrator every N seconds (configurable). Emits structured events to `events.jsonl`.                  |
| `diagnostician`   | Fingerprints failures by structural pattern. Hypothesizes root cause. Dispatches Surgeon when confidence ≥ 0.7. |
| `surgeon`         | Spawns a worktree, calls Cartographer + Forger + Tester, opens a PR. Self-bounded by `policy.operate.surgeon.max_workflows_touched_without_hitl`. |
| `auditor`         | Drift checker (XAML hash vs deployed package, license utilization, idle processes).                            |
| `concierge`       | Bridge between async humans and the swarm. Creates Action Center Form Tasks; routes responses back.             |

### Conductor (meta) — *the only agent that may invoke other agents*

Schedules cron jobs (auditor daily, strategist nightly, compost nightly), balances LLM token
budget across fleets, manages the worktree pool, enforces every HITL gate from
`policy.yaml::gates`, and runs the nightly compost step. **Cross-fleet handoffs always go
through the Conductor — there are no direct Discovery → Build calls.**

### Memory tiers

Three persistent stores, accessed only via `aurora-recall` (read) and `aurora-fingerprint`
(write):

1. **Project memory** at `.aurora/projects/<id>/` — per-bot state: PDD, ADR, selectors, tests, deploy history, failure log.
2. **Org memory** at `.aurora/org/` — cumulative: vendor-specific selector quirks, infra peculiarities, naming preferences.
3. **Skill memory** at `.aurora/learnings/` — append-only one-liners; consumed nightly by the compost step.

Hooks handle injection — agents never read memory manually. `pre-tool-load-memory.sh` injects
scoped slices before each tool call. `post-tool-fingerprint.sh` captures learnings after.

---

## Repo geometry

```
uipath-for-coding-agents/
├── README.md                       you are here
├── CLAUDE.md                       AURORA's project context (auto-loaded)
├── policy.yaml                     declarative configuration
├── policy.schema.json              JSON-schema for policy.yaml
├── pyproject.toml                  Python package + deps + ruff/mypy config
├── Makefile                        ci / test / lint / typecheck / policy targets
├── tasks.md                        24-task project breakdown (workstreams A-G + F)
├── PDD.md                          50-user-story spec
│
├── agents/                         19 subagent definitions (one .md per agent)
│   ├── conductor.md
│   ├── scout.md   curator.md   analyst.md   interviewer.md   strategist.md
│   ├── architect.md   cartographer.md   forger-{rpa,coded,agent,maestro}.md
│   ├── reviewer.md   tester.md
│   └── sentry.md   diagnostician.md   surgeon.md   auditor.md   concierge.md
│
├── skills/                         10 custom AURORA skills + manifests
│   ├── aurora-auth/   aurora-discover/   aurora-pdd/   aurora-fingerprint/
│   ├── aurora-replay/   aurora-promote/   aurora-recall/   aurora-compost/
│   └── aurora-policy/   aurora-deprecate/
│
├── lib/aurora/                     Python runtime
│   ├── cli.py                      `aurora start | status | policy | recall | …`
│   ├── conductor.py                cron + worktree pool + budget + gates
│   ├── sentry.py                   Orchestrator polling daemon
│   ├── fingerprint.py              fault clustering + sqlite store
│   ├── memory.py                   three-tier memory store
│   ├── policy.py                   policy.yaml loader + schema validator
│   ├── policy_live.py              live probes (Orchestrator + GitHub + catalog)
│   ├── promote.py                  HITL gate via Action Center Form Task
│   ├── compost.py                  nightly skill-PR opener
│   ├── recall.py                   scoped memory retrieval
│   ├── replay.py                   sandbox-folder twin replay
│   ├── auth.py                     UiPath OAuth + token sidecar
│   ├── uipath_client.py            httpx wrapper (OData + Maestro + Tasks)
│   ├── test_manager.py             Test Manager link automation
│   ├── tui/                        Textual TUI for `aurora status`
│   ├── playwright/                 Studio Web traffic capture + UI fallbacks
│   └── mcp/server.py               MCP server exposing aurora_* tools
│
├── examples/oss-supply-chain-defender/
│   ├── process.bpmn                BPMN 2.0 (no inline taskBindings)
│   ├── bindings.json               BPMN-task → coded artifact bindings
│   ├── Config.xlsx                 environment-dependent values
│   ├── break.sh   restore.sh       failure injection / rollback for the demo
│   ├── agents/                     2 Coded Agents (LangGraph + OpenAI Agents)
│   ├── coded/                      6 C# Coded Workflows
│   ├── workflows/                  XAML workflows
│   └── tests/                      Maestro test fixtures
│
├── webhook/github-check-run/       FastAPI webhook (HMAC verify + Maestro correlation)
│
├── tests/                          639 tests + 4 live integration tests
│   ├── unit/                       lib/aurora unit tests
│   ├── lint/                       schema + invariant tests (BPMN, hooks, uipath CLI, …)
│   ├── agents/                     contract tests for all 19 agents (T-G1..G4)
│   ├── coded/                      6 xUnit suites for C# Coded Workflows
│   ├── workflows/                  XAML lint tests
│   ├── docs/                       claims-mapping regression
│   └── integration/                live-tenant tests gated by UIPATH_INTEGRATION=1
│
├── docs/
│   ├── architecture.md
│   ├── demo-script.md              12-minute beat-by-beat walkthrough
│   ├── grill-2026-05-09.md         UiPath-doc grill verdicts
│   ├── runbook-aurora-start.md     5-minute live-verification recipe
│   ├── webhook-deploy.md           Cloudflare Tunnel + GitHub webhook setup
│   ├── maestro-publish-bridge.md   Studio Web traffic-capture runbook
│   ├── test-manager-linkage.md     Test Manager API rotation runbook
│   ├── submission-post.md          Submission narrative
│   └── submission-claims.json      Every load-bearing claim → on-disk artifact
│
├── hooks/                          Claude Code hooks (PreToolUse / PostToolUse / Notification / UserPromptSubmit)
└── .claude/
    ├── settings.json               hook registrations + tool denies
    ├── rules/aurora-conventions.md the 60+ rules
    └── plugins/                    AURORA Claude Code plugin manifests
```

---

## Convention discipline

`.claude/rules/aurora-conventions.md` injects **60+ rules** before every tool call. They cover
naming, structure, error handling, secrets, configuration, selectors, logging, coded
workflow/agent patterns, BPMN/DMN structure, and the AURORA-specific swarm conventions. The
Reviewer agent enforces them; merge blocks on any error-level violation.

A taste:

| ID         | Rule                                                                                                    |
| ---------- | ------------------------------------------------------------------------------------------------------- |
| `R.N.02`   | Argument prefixes are mandatory: `in_`, `out_`, `io_`. Never an unprefixed argument.                    |
| `R.S.02`   | REFramework's `SetTransactionStatus.xaml` is unmodified. If you think you need to change it, your design is wrong. |
| `R.E.02`   | `RetryScope` wraps every API call. NumberOfRetries ≥ 3, RetryInterval ≥ 5s.                              |
| `R.X.01`   | Credentials are always `SecureString`. `String` passwords are an instant lint fail.                      |
| `R.SE.01`  | Selectors are strict (single-find) only. A selector that matches 0 or > 1 elements is rejected.          |
| `R.M.02`   | Every User Task has a boundary timer with explicit timeout.                                              |
| `R.SW.02`  | Cross-fleet handoffs go through Conductor. No direct Discovery → Build calls.                            |
| `R.SW.05`  | HITL gates from `policy.yaml::gates` are absolute. Never bypass, even when "obvious."                    |
| `R.G.05`   | Compost-step skill PRs are NEVER auto-merged. Always HITL.                                               |

Reviewer-driven prompt-body lint (`tests/agents/test_all_agents_lint.py` — T-G4) codifies 10
additional rules over agent prompt bodies (e.g., R.G4.04: Build-fleet agents must reference the
canonical UiPath skill catalogue). The 10 rules collectively caught and fixed real drift in 22
of the 19 agent files during this build.

---

## Configuration

### `policy.yaml` (declarative — not prompts)

```yaml
identity:
  uipath_folder: ${UIPATH_FOLDER}
  action_catalog: ${UIPATH_ACTION_CATALOG}
  github_org: ${GITHUB_ORG}

routing:
  defaults:
    high_stakes: claude-opus-4-7
    mid_stakes: claude-sonnet-4-6
    continuous: claude-haiku-4-5-20251001
  bindings:
    architect: high_stakes
    surgeon: high_stakes
    forger-rpa: mid_stakes
    sentry: continuous
    # … all 19 agents bound here

worktree_pool:
  max_concurrent: 4

budget:
  daily_usd: ${AURORA_DAILY_BUDGET_USD}

operate:
  sentry: { poll_interval_seconds: ${AURORA_SENTRY_INTERVAL} }
  surgeon: { max_auto_fixes_per_day: 5, max_workflows_touched_without_hitl: 3 }
  maestro: { waitforci_timeout_iso8601: PT4H }

gates:
  - name: prod_publish
    triggers: [forger-maestro.publish, forger-coded.publish]
    timeout_hours: 24
  - name: emergency_patch
    triggers: [surgeon.dispatch_critical]
    timeout_hours: 4
  - name: skill_compost_pr
    triggers: [conductor.compost]
    auto_merge: false           # NEVER auto-merge compost PRs (R.G.05)
  # … 5 gates total
```

Fully JSON-schema-validated against [`policy.schema.json`](policy.schema.json) on `aurora policy
validate`. Live-probed against the real tenant by `aurora policy validate --strict --live`.

### `.env`

Two flavors of secrets, kept separate:

- **UiPath**: OAuth client-credentials via the External Application — `UIPATH_CLIENT_ID` +
  `UIPATH_CLIENT_SECRET`. The skill `aurora-auth` mints + refreshes the access token; writes it
  to `UIPATH_ACCESS_TOKEN` so the `uipath` CLI works without re-auth.
- **Claude**: subscription OAuth via `~/.claude/credentials.json`. Run `claude login` once on
  the VPS. Both Claude Code (Build fleet) and the Claude Agent SDK (Operate-fleet daemons) read
  this file. **There is no `ANTHROPIC_API_KEY`** — the deny rule in `.claude/settings.json`
  enforces this.

See [`.env.example`](.env.example) for the full surface (UiPath, GitHub, Slack, NVD, OSV,
Scorecard, AURORA runtime knobs).

---

## What broke or surprised us

The build surfaced **five silent-degradation bugs** that no test suite caught — because each one
lived in the gap between the production code and the runtime (hooks failing, fictional SDK
methods, JQ paths against the wrong event schema, identity endpoint at the wrong scope).
Documented in [`docs/submission-post.md`](docs/submission-post.md) "What broke or surprised
me." Each is now closed and **regression-tested in `make ci`** so the bug class can't return.

A few highlights:

- **Hooks shipped without `+x` since the initial commit** (project-side `.claude/settings.json`
  registered four hooks but the scripts were `100644`). Every PreToolUse / PostToolUse hook
  silently 126'd, flooding the UI with `mkdir: cannot create '/opt/aurora': Permission denied`.
  Triaged in commits `d2edb4e`, `43182d6`, `26c80b1` (B1-B5 of the hook triage). New regression
  test `tests/lint/test_hooks_executable_and_clean.py` smoke-runs every hook in a stripped env
  to catch this from ever happening again.
- **`UiPathClient` called `sdk.api_client.get(…)`** — a method that doesn't exist on the real
  uipath-python SDK. Unit tests with MagicMock auto-created any attribute name, so the bug
  never fired in CI. It only surfaced the moment Sentry's first tick hit a live Orchestrator
  (caught by the F3 5-min live run, which logged 11 `sentry_self_error` events before this fix).
  Refactored to bypass `sdk.api_client` and use direct `httpx.Client` against the OData/Maestro
  surface.
- **`derive_identity_endpoint` was wrong for cloud.uipath.com.** Built tenant-scoped token URLs
  like `https://cloud.uipath.com/{acct}/{tenant}/identity_/connect/token` and got 404. The
  OpenID-discovery doc says cloud's identity endpoint is at the host root, not the tenant root.
  Fixed in `7a20b78` plus 4 regression tests.
- **The hook's JQ paths didn't match Claude Code's real PostToolUse schema.** The hook ran fine
  but the failure-classification branch never fired on real events. Fixed by switching to
  `.tool_response.isError` and friends, plus three frozen real-shape fixtures
  (`tests/lint/fixtures/hooks/posttooluse_*.json`).

---

## Known limits and future work

Honest scope statements:

- **The 12-minute demo video isn't recorded yet.** All other artifacts shipped; the video is
  the last asset.
- **F4 / F6 / F7** (full Maestro flow with WaitForCI + Critical sub-process + 12-min demo dress
  rehearsal) require a Cloudflare trial tunnel and a deployed Maestro process. Code paths are
  built and unit-tested; live verification is a runbook step.
- **Maestro publish bridge** (`MaestroService.publish_maestro_project`) currently uses a
  synthetic captured-request fixture. First live publish requires running
  `lib/aurora/playwright/capture.py` once interactively to capture the real Studio Web request
  shape. Documented in [`docs/maestro-publish-bridge.md`](docs/maestro-publish-bridge.md).
- **Test Manager linkage** uses `/test_/api/v1/` — a documented surface but the exact endpoint
  shape may rotate. The Playwright UI fallback in `lib/aurora/playwright/test_manager_ui.py` is
  the rotation insurance.
- **`uipath-openai-agents`** is pinned to `0.0.10` (the current PyPI version). Upgrade to
  `0.1.x` once it ships.

---

## Built on

- [`UiPath/skills`](https://github.com/UiPath/skills) — the seven official skills, all installed
- [`UiPath/uipath-python`](https://github.com/UiPath/uipath-python) — every Orchestrator interaction goes through it (read paths) or through its httpx-compatible bearer scheme (write paths)
- [`uipath` CLI](https://uipath.github.io/uipath-python/) — `init` / `pack` / `publish`
- [`Anthropic Claude`](https://claude.com) via subscription OAuth (no API key)
- [`UiPath/uipath-langchain-python`](https://github.com/UiPath/uipath-langchain-python) — for the LangGraph Coded Agent path
- [`UiPath/uipath-openai-agents`](https://pypi.org/project/uipath-openai-agents/) — for the OpenAI Agents SDK Coded Agent path

Plus pattern inspirations (no code reused, only ideas):
[Obra Superpowers](https://github.com/obra/superpowers) (TDD discipline + worktrees),
[Matt Pocock skills](https://github.com/mattpocock/skills) (lifecycle commands),
[Ouroboros](https://github.com/ouroboros) (Socratic interview, ambiguity scoring),
[Factory.ai Missions](https://docs.factory.ai/) (separation-of-concerns, mission-mode loops).

---

## Contributing

PRs welcome. Some notes:

- **Verifiable claims.** Every load-bearing claim in `docs/submission-post.md` maps to a real
  artifact via [`docs/submission-claims.json`](docs/submission-claims.json), enforced by
  [`tests/docs/test_submission_claims.py`](tests/docs/test_submission_claims.py). If you rename a
  referenced artifact without updating the claims map, CI breaks.
- **`make ci` is the merge gate.** It runs lint (`ruff`), typecheck (`mypy --strict`), the full
  test suite, and `aurora policy validate --strict`. PRs from external contributors should hit
  CI on the parent fork's runner; live-tenant tests under `tests/integration/` are gated by
  `UIPATH_INTEGRATION=1`.
- **TDD discipline.** Every new behavior, bug fix, or refactor that touches logic gets a
  failing test first. Red → green → refactor.
- **Convention discipline.** The 60+ rules in `.claude/rules/aurora-conventions.md` apply to PR
  contributions too. The Reviewer agent (or a human reviewer using its rule set) checks compliance.

---

## Acknowledgments

- The **UiPath product team** for `UiPath/skills`, the `uipath` CLI, and the `uipath-python` SDK.
- **@alexandru** and **@Simona_Boboc** for shaping this challenge.
- The community feedback that turned an early "just one more bot" prototype into a swarm.

---

## License

[MIT](LICENSE).
