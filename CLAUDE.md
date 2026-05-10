# AURORA

Autonomous UiPath RPA Operations & Reasoning Agency — a 15-agent swarm that builds, tests, deploys, monitors, and self-heals UiPath automations end-to-end. This file is the project context Claude Code loads on every session.

## What you're working on

You're a coding agent in an organization. Your peers — fourteen of them, defined in `agents/` — each have one job. Together, you ship and operate UiPath automations without a human writing code. A human sets policy in `policy.yaml`, approves risk gates through Action Center, and inspects results.

The current build target is the **Open-Source Supply-Chain Defender**, a Maestro-orchestrated agentic process that monitors a GitHub organization's dependency graph, triages vulnerabilities against public feeds (NVD, OSV, GitHub Advisory, OpenSSF Scorecard), and ships patches with HITL gates on production-affecting fixes. See `examples/oss-supply-chain-defender/`.

## The swarm — at a glance

Three fleets plus a Conductor. They run **concurrently, not sequentially**.

**Discovery (5 agents).** What should we automate?

- `scout` — passive sensor; reads Slack/Jira/email fixtures, surfaces friction
- `curator` — deduplicates, clusters, maintains the candidate backlog
- `analyst` — writes PDDs, scores ROI
- `interviewer` — Socratic Q&A when ambiguity is high
- `strategist` — quarterly retrospective; recommends consolidation/deprecation

**uild (8 agents — 4 plus 4 forger sub-specialists).** Idea ? running bot.

- `architect` — picks the UiPath pattern (Sequence / REFramework / Coded / Coded Agent / Maestro)
- `cartographer` — Object Repository, strict selectors via Playwright MCP and `inspect-ui-tree.ps1`
- `forger-rpa` — uses skill `uipath-rpa-workflows` (XAML)
- `forger-coded` — uses skill `uipath-coded-workflows` (C#)
- `forger-agent` — uses skill `uipath-coded-agents` (LangGraph / OpenAI Agents / LlamaIndex)
- `forger-maestro` — emits BPMN 2.0 XML + DMN tables, publishes via `uipath-platform`
- `reviewer` — REFramework discipline, lint, conventions
- `tester` — Test Manager test cases from acceptance criteria

**Operate (5 agents).** Running bots ? SLA-met fleet.

- `sentry` — polls Orchestrator via the SDK; emits structured events
- `diagnostician` — clusters failures by fingerprint; hypothesizes root cause
- `surgeon` — opens PRs to fix; coordinates with Cartographer + Forger + Tester
- `auditor` — drift, license/utilization, deprecation candidates, governance pre-publish
- `concierge` — UiPath Action Center bridge; routes async approvals back into agent state

**Meta.**

- `conductor` — schedules, balances LLM token budget, manages worktree pool, enforces gates, runs the nightly compost step

## Conventions you must follow

### UiPath conventions (REFramework discipline)

- **PascalCase** for variables; **camelCase** for arguments only inside coded workflows.
- **Argument prefixes** are mandatory: `in_`, `out_`, `io_`. Never an unprefixed argument.
- **Workflow filenames** are PascalCase with app prefix: `Acme_Login.xaml`, not `Login.xaml`.
- **Try/Catch** wraps every external call. **RetryScope** wraps every API call.
- **Selectors** are strict (single-find), not fuzzy. They live in the Object Repository, not inline.
- **Config.xlsx** drives URLs, asset names, queue names, and any environment-dependent value. Nothing hardcoded in workflows.
- **Credentials** are always `SecureString`, fetched via `GetRobotCredential` at minimum scope. Never passed as arguments between workflows.
- **REFramework rules**: don't modify `SetTransactionStatus`. `InitAllApplications` opens apps and reaches ready state. `Process.xaml` and action workflows attach with `OpenMode="Never"`.
- **Browser**: incognito by default; one browser instance per app; navigate by URL via `NGoToUrl`, not by clicking link paths.

### AURORA conventions

- **One agent, one job.** If you find yourself doing two things, hand the second off to the right peer.
- **Policy over prompts.** If a decision is configurable, it lives in `policy.yaml`, not in your prompt.
- **Memory tiers.** Read scoped slices via `aurora-recall`; write learnings via `aurora-fingerprint`. Don't dump global memory into context.
- **HITL gates are non-negotiable.** Never bypass a gate from `policy.yaml`. If a step matches a gate trigger, you stop and route through `concierge`.
- **Worktrees for parallel work.** Forger sub-fleet runs in `${AURORA_WORKTREE_DIR}/<job-id>/`, never in the main checkout.

## When to use which skill

Seven official UiPath skills (installed via `uipath skills install`) and ten AURORA skills (in `skills/`). Pick the right one:

| Task | Skill |
|---|---|
| Build XAML workflow | `uipath-rpa-workflows` |
| Build C# coded automation | `uipath-coded-workflows` |
| Build Python agent (LangGraph / OpenAI Agents) | `uipath-coded-agents` |
| Build a Flow (.flow JSON) | `uipath-flow` |
| Auth, Orchestrator ops, package lifecycle | `uipath-platform` |
| Build a Coded App | `uipath-coded-apps` |
| Desktop / browser UI inspection or test | `uipath-servo` |
| Mint or refresh UiPath OAuth tokens | `aurora-auth` |
| Read scoped memory | `aurora-recall` |
| Write a learning to memory | `aurora-fingerprint` |
| Replay an instance in a sandbox folder | `aurora-replay` |
| HITL gate via Action Center | `aurora-promote` |
| Process retirement | `aurora-deprecate` |
| Validate policy.yaml or run a policy dry-run | `aurora-policy` |
| Author a PDD with ambiguity scoring | `aurora-pdd` |
| Extract friction signals from a fixture | `aurora-discover` |
| Compost daily learnings into a skill PR | `aurora-compost` |

When in doubt, read the skill's `SKILL.md` first. Skills carry their own context; don't try to remember everything globally.

## Memory model

Three persistent stores, accessed only via `aurora-recall` and `aurora-fingerprint`:

1. **Project memory** at `.aurora/projects/<id>/` — per-bot state: PDD, ADR, selectors, tests, deploy history, failure log.
2. **Org memory** at `.aurora/org/` — cumulative: vendor-specific selector quirks, infra peculiarities, naming preferences.
3. **Skill memory** at `.aurora/learnings/` — append-only one-liners; consumed nightly by `conductor` for the compost step.

Hooks handle injection — don't read memory manually. `pre-tool-load-memory.sh` injects scoped slices before each tool call. `post-tool-fingerprint.sh` captures learnings after.

## Auth model

Two distinct authentications — don't mix them up:

- **UiPath**: OAuth client-credentials via the External Application registered in Automation Cloud. Skill `aurora-auth` mints and refreshes tokens, reading `UIPATH_CLIENT_ID` + `UIPATH_CLIENT_SECRET` from `.env`. Writes the live access token to `UIPATH_ACCESS_TOKEN` so the `uipath` CLI works without re-auth.
- **Claude**: subscription OAuth via `~/.claude/credentials.json`. Run `claude login` once on the VPS. Both Claude Code (Build fleet) and the Claude Agent SDK (Operate-fleet daemons) read this file.

There is no `ANTHROPIC_API_KEY`. Don't introduce one.

## How a typical job runs

1. `scout` flags a friction signal from a configured Discovery source.
2. `curator` deduplicates against the backlog.
3. `analyst` writes a PDD, scores it. Below `min_score_for_build`, log only.
4. If ambiguity is high, `interviewer` pings the human via Slack or Action Center.
5. `architect` writes an ADR — pattern selection.
6. Forger sub-fleet builds in parallel worktrees, coordinated by `conductor`.
7. `cartographer` populates the Object Repository.
8. `tester` writes Test Manager cases from the seed's acceptance criteria.
9. `reviewer` lints, blocks merge on red.
10. `conductor` invokes `aurora-promote` for the prod gate. `concierge` creates the Action Center task and waits.
11. On approval, deploy via `uipath publish`.
12. `sentry` watches the live process. `diagnostician` clusters failures. `surgeon` opens PRs. `auditor` checks drift.
13. Nightly: `conductor` runs the compost step — composes a PR against `skills/` based on the day's `learnings.jsonl`.

## Demo (the use case driving everything)

`examples/oss-supply-chain-defender/` contains the Maestro process AURORA builds. The shape:

- **Start (Timer)** — every 6 hours
- **RPA Task** — resolve repos, fetch lockfiles
- **Parallel Gateway** with four branches: Vuln Lookup (AI Agent), Maintainer Health (AI Agent), Typosquat Check (RPA), License Drift (RPA)
- **DMN Decision Table** — severity matrix
- **Exclusive Gateway** — Critical / High / Medium / Low
- **Critical sub-process** — Triage (AI) ? Action Center approval (boundary timer 4h) ? Patch PR (RPA) ? CI wait ? auto-merge if green
- **High sub-process** — auto-PR with version bump
- **End** — Insights emit

See `docs/demo-script.md` for the 12-minute beat sheet.

## Anti-patterns

- **Don't bypass policy.yaml.** Even for "obvious" cases. The whole point is reproducibility.
- **Don't reach across fleet boundaries.** A Discovery agent can't directly invoke a Build agent. They communicate via `conductor` and the backlog.
- **Don't introduce new model providers without updating `routing.bindings`.** No silent multi-model decisions.
- **Don't write XAML by hand.** Use `forger-rpa` and the `uipath-rpa-workflows` skill. Hand-written XAML is an instant lint fail.
- **Don't merge a compost-step skill PR yourself.** It's HITL-gated for a reason — the swarm's skills should change deliberately.
- **Don't store secrets in memory or learnings.** Fingerprints are sanitized; if you need a credential, fetch via Orchestrator Asset.

## Helpful commands
aurora start                 # boot the swarm
aurora status                # TUI dashboard
aurora policy validate       # lint policy.yaml
aurora policy dry-run        # show what would happen with the current backlog
aurora recall <query>        # search org memory
aurora feedback              # send context + last action to UiPath team

## Attribution

Built on UiPath's official skills (`UiPath/skills`) and Python SDK (`UiPath/uipath-python`). Pattern inspirations: Obra Superpowers (TDD/worktrees), Matt Pocock skills (planning discipline), Ouroboros (Socratic interview, ambiguity scoring), Factory.ai Missions (separation-of-concerns). Reference-only inspirations (not reused): `marcelocruzrpa/uipath-ai-skills`, `mlbrilliance/Autonomous-RPA-Architect`.