# AURORA

**Most submissions to this challenge are coding agents that build one bot. AURORA is an org chart that runs forever.**

19 agents in three concurrent fleets — Discovery, Build, Operate — coordinated by a Conductor that schedules, balances, gates, and runs a nightly **compost step** that proposes upgrades to the swarm's own skills. From a Slack message to a deployed UiPath Maestro process to a self-healed production failure to a draft skill PR, with **two human approvals** total.

```
                                          policy.yaml
                                              │
    ┌──── Discovery ────┐    ┌────── Conductor ──────┐    ┌──── Operate ──────┐
    │  scout            │    │ schedules · gates    │    │  sentry           │
    │  curator          │ ◀──┤ balances · composts  ├──▶ │  diagnostician    │
    │  analyst          │    └──────────┬──────────┘    │  surgeon          │
    │  interviewer      │               │                │  auditor          │
    │  strategist       │               ▼                │  concierge        │
    └───────────────────┘    ┌──── Build ────┐           └───────────────────┘
                             │  architect    │
                             │  cartographer │
                             │  forger-rpa   │
                             │  forger-coded │
                             │  forger-agent │
                             │  forger-maestro│
                             │  reviewer     │
                             │  tester       │
                             └──────────────┘
```

The three loops never pause for each other. While Build is shipping a new bot, Operate is healing a previously-shipped one, and Discovery is scoring tomorrow's candidates from a configured Slack channel.

## Why this is different

1. **Three concurrent fleets, not phases.** Every other coding-agent demo for UiPath models the lifecycle as Build → Run → Done. AURORA models it as Discovery + Build + Operate, all live at once. That's the actual shape of an RPA Center of Excellence.
2. **Self-evolving skills.** Every agent writes one-line learnings as it works. The nightly compost step filters for ≥3 occurrences across ≥2 projects with consistent rationale and opens a real `gh pr create --draft` against this repo's `skills/<name>/SKILL.md`. HITL-gated, never auto-merged. AURORA's skills get measurably better with use.
3. **Verified live.** `aurora policy validate --strict --live` proves Orchestrator + GitHub + Action Center are reachable. `aurora start` runs ≥ 5 minutes against the real tenant with **zero ERROR entries**, every Sentry tick a 200 OK against `/odata/Folders`, `/odata/Jobs`, `/maestro_/api/instances`. **634 unit/lint/agents/workflow tests** in CI; six xUnit suites for the C# Coded Workflows. No mocks in production paths.

## What's inside

Built on the official UiPath surface — every actor type exercised:

| UiPath capability | AURORA artifact |
|---|---|
| Maestro (BPMN 2.0 + DMN) | [`examples/oss-supply-chain-defender/process.bpmn`](examples/oss-supply-chain-defender/process.bpmn) |
| RPA workflow (XAML) | [`workflows/License/CheckLicenseDrift.xaml`](examples/oss-supply-chain-defender/workflows/License/CheckLicenseDrift.xaml) |
| Coded Workflow (C#) | [`coded/Typosquat`](examples/oss-supply-chain-defender/coded/Typosquat/), [`coded/ResolveLockfiles`](examples/oss-supply-chain-defender/coded/ResolveLockfiles/), [`coded/Notify`](examples/oss-supply-chain-defender/coded/Notify/), [`coded/OpenPatchPR`](examples/oss-supply-chain-defender/coded/OpenPatchPR/), [`coded/OpenAutoPR`](examples/oss-supply-chain-defender/coded/OpenAutoPR/), [`coded/PostPendingComment`](examples/oss-supply-chain-defender/coded/PostPendingComment/) |
| Coded Agent (Python) | [`agents/maintainer-health`](examples/oss-supply-chain-defender/agents/maintainer-health/) (OpenAI Agents SDK), [`agents/vuln-lookup`](examples/oss-supply-chain-defender/agents/vuln-lookup/) (LangGraph) |
| Action Center (Form Tasks) | [`lib/aurora/promote.py`](lib/aurora/promote.py), [`templates/`](skills/aurora-promote/templates/) |
| Test Manager linkage | [`lib/aurora/test_manager.py`](lib/aurora/test_manager.py) |
| Maestro publish bridge | [`lib/aurora/uipath_client.py:publish_maestro_project`](lib/aurora/uipath_client.py), [`lib/aurora/playwright/`](lib/aurora/playwright/) |
| Webhook for `check_run.completed` → Maestro correlation | [`webhook/github-check-run/`](webhook/github-check-run/) |

Plus all 7 official UiPath skills (`uipath-rpa-workflows`, `uipath-coded-workflows`, `uipath-coded-agents`, `uipath-flow`, `uipath-platform`, `uipath-coded-apps`, `uipath-servo`) and 10 custom AURORA skills under [`skills/`](skills/).

## Try it without a tenant (5 min)

```bash
git clone https://github.com/mlbrilliance/uipath-for-coding-agents.git
cd uipath-for-coding-agents
uv sync                                  # Python deps
.venv/bin/aurora start --skip-daemons    # boot policy + cron registry
make ci                                  # 634 tests + lint + typecheck + policy-strict
```

Expected: `aurora start --skip-daemons` exits 0 with the boot banner; `make ci` returncode 0.

## Run it live (with a tenant)

```bash
cp .env.example .env             # fill in UIPATH_*, GITHUB_*, AURORA_*
claude login                     # subscription OAuth → ~/.claude/credentials.json
ln -s CLAUDE.md AGENTS.md        # for Codex/Cursor compat
uipath skills install            # interactive — pick all 7 UiPath skills
aurora policy validate --strict --live    # 3/3 probes (Orchestrator + GitHub + Action Center catalog)
aurora start                     # boots the Conductor + Sentry; daemonizes
aurora status                    # TUI dashboard
```

The runbook for a 5-minute live verification with the exact `grep` recipe to assert "no ERROR entries" lives at [`docs/runbook-aurora-start.md`](docs/runbook-aurora-start.md).

## The demo

The 12-minute demo at [`docs/demo-script.md`](docs/demo-script.md) covers the full lifecycle in one take, with three concurrent timelines visible. Two human approvals total — production publish, and emergency patch. Everything else is autonomous, including:

- A real GitHub PR opened by the `OpenPatchPR` Coded Workflow.
- A real Action Center Form Task in the `aurora_supply_chain_approvals` catalog.
- A real Sentry-detected fault from `./break.sh` injecting an invalid `GITHUB_TOKEN`, fingerprinted by the Diagnostician as `auth-failed/token-expired`, and resumed by the Surgeon rotating to `GITHUB_TOKEN_FALLBACK`.
- A draft PR proposing a skill update from the nightly compost step.

Demo target: **OSS Supply-Chain Defender** — a Maestro process that monitors a GitHub org's lockfiles against NVD, OSV, and the GitHub Advisory Database, triages findings against a DMN severity matrix, and ships patches with HITL gates on production-affecting fixes.

## Architecture in two minutes

- **Discovery (5 agents)** — passive sensor + curation + scoring.
  Slack/Jira/email signals → friction-signal candidate → deduplicated backlog → PDD with ROI score → ambiguity check → optional Socratic Q&A.
- **Build (8 agents)** — pattern selection + parallel worktrees.
  Architect picks Sequence / REFramework Performer / REFramework Dispatcher / Coded Workflow (C#) / Coded Agent (Python) / Maestro / Action Center / API Workflow / Document Understanding. Forger sub-fleet builds in parallel git worktrees under `${AURORA_WORKTREE_DIR}/<job-id>/`. Reviewer enforces 60+ rules from `.claude/rules/aurora-conventions.md`. Tester emits Studio test packages and links them via the Test Manager Select-Automation flow.
- **Operate (5 agents)** — continuous, no human in the loop until something demands one.
  Sentry polls Orchestrator every N seconds. Diagnostician fingerprints faults by structural pattern; clusters with confidence ≥ 0.7 dispatch automatically. Surgeon spins a worktree, calls Cartographer for re-inspection, calls a Forger for regeneration, opens a PR. Auditor runs drift checks. Concierge bridges to Action Center for HITL.
- **Conductor** — schedules sprints, balances LLM token budget across fleets, manages the worktree pool, enforces every gate from `policy.yaml::gates`, and runs the nightly compost step.

Three persistent memory tiers, accessed only via `aurora-recall` (read) and `aurora-fingerprint` (write). Five HITL gates in `policy.yaml` — every gate routes through Concierge to Action Center.

## What broke or surprised us

The build surfaced five silent-degradation bugs that no test suite caught (because they all lived in the gap between the production code and the runtime — hooks failing, fictional SDK methods, JQ paths against the wrong event schema). Each is now closed and **regression-tested in `make ci`** so the bug class can't return. See [`docs/submission-post.md`](docs/submission-post.md) "What broke or surprised me" for the story.

## Contributing

PRs welcome. Verifiable claims: every load-bearing claim in [`docs/submission-post.md`](docs/submission-post.md) maps to a real artifact via [`docs/submission-claims.json`](docs/submission-claims.json), enforced by [`tests/docs/test_submission_claims.py`](tests/docs/test_submission_claims.py). If you rename a referenced artifact without updating the claims map, CI breaks.

## License

MIT. Built on top of [UiPath/skills](https://github.com/UiPath/skills) and [UiPath/uipath-python](https://github.com/UiPath/uipath-python). Inference via Claude subscription OAuth — no API key.
