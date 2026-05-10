# AURORA — Architecture

> *Autonomous UiPath RPA Operations & Reasoning Agency.* A 19-agent swarm that builds, tests, deploys, monitors, and self-heals UiPath automations end-to-end. This document describes the system shape, the rationale for each non-obvious decision, and where to extend.

## One-paragraph summary

A human writes `policy.yaml`. AURORA reads it. From there, three concurrent fleets — Discovery (5 agents), Build (8), Operate (5) — coordinated by a Conductor (1) and gated by Action Center, take an automation from a Slack message to a running Maestro process, then keep it running across selector drift, token rotation, API changes, deprecation, and continuous self-improvement. The swarm uses UiPath's official `uipath-python` SDK, the official `UiPath/skills` skill catalog, the `uipath` CLI, and ten custom AURORA skills. Inference is Claude (subscription OAuth, no API key); auth into UiPath is OAuth client-credentials.

## The three concurrent loops

These run in parallel, always. There's no "phase" handoff because a real CoE doesn't have phases — it has a backlog, a build queue, and a production fleet, all live at once.

```
                   policy.yaml                   ┌── Discovery loop ──┐
                       │                         │  scout             │
                       ▼                         │  curator           │
   ┌──────────── Conductor ──────────────┐       │  analyst           │
   │  schedules, balances, gates, composts│ ───▶  │  interviewer       │
   └──────────────────┬──────────────────┘       │  strategist        │
                      │                          └────────────────────┘
                      ▼
              ┌── Build loop ───┐
              │  architect       │
              │  cartographer    │           ┌── Operate loop ────┐
              │  forger-rpa      │           │  sentry            │
              │  forger-coded    │ ◀───────▶ │  diagnostician     │
              │  forger-agent    │           │  surgeon           │
              │  forger-maestro  │           │  auditor           │
              │  reviewer        │           │  concierge         │
              │  tester          │           └────────────────────┘
              └─────────────────┘
                      │
                      ▼
              git worktrees                     events.jsonl
              .aurora/projects/<id>             fingerprints.db
                                                .aurora/learnings/
                                                       │
                                                       ▼
                                                Compost step (nightly)
                                                       │
                                                       ▼
                                                skill-update PR (HITL)
```

The arrows between Build and Operate are bidirectional: when Operate detects a fault, Surgeon dispatches the Build sub-fleet (Cartographer to re-inspect, Forger to regenerate, Tester to regression). When Build deploys, Operate immediately starts watching.

## Why concurrent loops, not phases

Three reasons:

1. **CoEs are continuous.** Discovery shouldn't pause while Build ships. Operate shouldn't sleep waiting for the next build.
2. **Self-healing requires it.** The Operate fleet must be live the moment a bot ships, not after Build's queue drains.
3. **It exposes natural backpressure.** If Operate is overwhelmed, Conductor pauses non-critical Discovery; if Build falls behind, Discovery slows its scoring; if Discovery is empty, Operate gets more attention. The same Conductor that schedules dispatches the throttle.

## The Conductor's three jobs

1. **Dispatch.** Read backlog, pick what's ready, spawn the right agent in the right worktree.
2. **Balance.** Token-budget per fleet. When Build is hot, throttle Discovery's scoring. When Operate is on fire, freeze Build entirely until Surgeon clears the queue.
3. **Compost.** Nightly, read `.aurora/learnings/<date>.jsonl`, cluster patterns, propose PRs against the swarm's own skills. Always HITL-gated. **The mechanism that makes the swarm get smarter with use.**

The Conductor never writes XAML, never picks a pattern, never approves a gate. It's the conductor of a real orchestra — silent during the music, essential to it sounding right.

## Memory model

Three tiers, each with a defined access pattern:

| Tier | Where | What | Read by | Written by |
|---|---|---|---|---|
| Project | `.aurora/projects/<id>/` | PDD, ADR, review, tester-coverage, triage notes | Build + Operate (scoped to their job) | Each agent owns a slice |
| Org | `.aurora/org/` | Vendor quirks, naming preferences, patterns that worked | All fleets | Append-only via `aurora-fingerprint` for facts; explicit human edits welcome |
| Skill | `.aurora/learnings/<date>.jsonl` + `fingerprints.db` | One-line learnings + structured fingerprints | Conductor (compost), Diagnostician (kNN cluster lookup) | Append-only |

Reading goes through `aurora-recall` for ranking and audit. Writing goes through `aurora-fingerprint` for the structured cluster index, plus direct file appends for narrative learnings. **Direct `cat` of `.aurora/` is forbidden by the conventions** — scoping is the whole point.

## Why Maestro for the demo, not REFramework

The challenge accepts any pattern. Why this one?

- **Three actor types collaborate.** RPA bots, AI agents, and humans (Action Center). Maestro is the only pattern that orchestrates all three with first-class governance.
- **Long-running and event-driven.** The Defender process spans seconds (auto-fix) to hours (HITL approval). A pure RPA flow would have to fake this with queues and heartbeats; BPMN models it natively.
- **DMN externalises decisions.** The severity matrix and auto-merge policy are DMN tables, not agent prompts. Auditable, editable by non-developers, version-controlled.
- **It's where UiPath is heading.** Coded Agents, Coded Apps, and Maestro are the trio UiPath is leaning into. The challenge implicitly rewards exercising these.

REFramework is great for a single transactional bot. AURORA builds those when Architect's ADR calls for it; the demo just doesn't need one.

## Auth model

Two distinct authentications:

1. **UiPath** — confidential External Application, OAuth client-credentials grant. `aurora-auth` skill mints fresh tokens at runtime, writes to `.env` (so `uipath` CLI sees them) and `~/.uipath/aurora-token.json` (so the daemon's in-process cache sees them). Tokens last 1 hour; AURORA refreshes 5 minutes before expiry.

2. **Claude** — subscription OAuth via `claude login`. Credentials live at `~/.claude/credentials.json`. **Both Claude Code (Build fleet via subagents) and the Claude Agent SDK (Operate-fleet daemons) read this file.** No `ANTHROPIC_API_KEY`. The `.claude/settings.json` even adds a deny-rule on `anthropic.com/v1/messages` to enforce this — any agent that tries direct API access fails loudly.

## Multi-tier model routing

Three Claude tiers, picked per agent role:

| Tier | Model | Used for | Why |
|---|---|---|---|
| `high_stakes` | Opus | Architect, Diagnostician, Strategist, Conductor | Rare, expensive decisions; one bad call is worth the cost of being right |
| `mid_stakes` | Sonnet | All Forger sub-specialists, Reviewer, Tester, Cartographer, Interviewer, Analyst, Auditor, Surgeon | The hot path; needs to be both fast and good |
| `continuous` | Haiku | Sentry, Curator, Scout, Concierge | Always-on; cheap matters more than peak quality |

The bindings live in `policy.yaml::routing.bindings`. Override per agent without touching code.

## Hooks

Four hooks enforce invariants the agents would otherwise have to remember:

- **`PreToolUse`** — `pre-tool-load-memory.sh` invokes `aurora-recall` to inject scoped memory before the agent acts. Agents don't need to remember to fetch; they just see relevant context.
- **`PostToolUse`** — `post-tool-fingerprint.sh` captures any explicit `learning:` lines from the agent's output, classifies any failures into the fingerprint index. Agents can't *forget* to log.
- **`UserPromptSubmit`** — `user-prompt-deploy-gate.sh` detects risk keywords (publish, prod, delete, deprecate, force push) and injects a gate reminder. Agents can't accidentally drift past a `policy.yaml` gate by virtue of not reading it.
- **`Notification`** — `notification-action-center.sh` routes Claude Code's blocking-prompt events to Concierge so HITL waits surface in Action Center, not the terminal.

## Self-evolving skills (the compost step)

This is the design's most novel idea. Every agent's `learning:` lines accumulate in `.aurora/learnings/<date>.jsonl`. Nightly, Conductor:

1. Reads the day's learnings
2. Clusters by skill / agent / fingerprint
3. Filters: only patterns with **≥ 3 occurrences across ≥ 2 projects with consistent rationale**
4. For each surviving cluster, opens a GitHub PR against `skills/<skill>/SKILL.md` (or, for fingerprint patterns, against `skills/aurora-fingerprint/scripts/cluster.py::derive_refinement`)
5. Routes through `aurora-promote` with `kind: skill_compost_pr` — **always HITL, never auto-merge**

The result: AURORA's skills get measurably better with use, but only via human-reviewed, version-controlled changes. **No public RPA tooling does this.** It's the most defensible novelty for the Innovation criterion.

## HITL gates as policy, not vibes

Every gate is in `policy.yaml::gates`. The form templates live in `skills/aurora-promote/templates/<kind>.json`. The implementation is `lib/aurora/promote.py`. Three things make this robust:

1. **Declarative.** No agent decides whether a step is risky enough for HITL — the policy says.
2. **Async-safe.** Concierge bridges the always-running swarm and asynchronous humans. The pause-resume pattern works because Maestro's User Tasks already do; AURORA leans on it.
3. **Audit-trail.** Every gate creates a Form Task in the catalog `aurora_supply_chain_approvals` (folder-scoped, encrypted-optional). Action Center is the source of truth for who approved what when.

## What's deliberately stubbed

These are intentional v0.2 boundaries:

- **`aurora.replay`** — sandbox-folder twin replay. Returns `{stub: true}` from the MCP for now.
- **TUI dashboard** — `aurora status --once` and `--json` work; the live Textual UI lands later.
- **`aurora.cli.cmd_compost`** — prints what it would do; doesn't open PRs yet.
- **MaintainerHealth Coded Agent** — referenced in BPMN; mirror of `vuln-lookup` with different tools/prompts.
- **TyposquatCheck and ResolveLockfiles coded workflows** — referenced; demo runs use the fixture overrides.
- **GitHub webhook handler** for the `WaitForCI` Receive Task — fixture in tests; small Lambda or Worker in prod.

Each is a known boundary, mentioned where it's relevant.

## Where to extend

| You want to | Touch |
|---|---|
| Add a new agent role | `agents/<name>.md`, `policy.yaml::routing.bindings`, `lib/aurora/recall.py::AGENT_DEFAULTS` |
| Add a new HITL gate | `policy.yaml::gates`, `skills/aurora-promote/templates/<kind>.json` |
| Add a new failure-fingerprint kind | `lib/aurora/fingerprint.py::CANONICAL_KINDS` and `derive_kind`/`derive_refinement` |
| Add a new Discovery source | `lib/aurora/sources/<kind>.py`, `policy.schema.json::discovery.sources`, `policy.yaml::discovery.sources` |
| Add a new Forger sub-specialist | `agents/forger-<x>.md`, `architect.md` decision rubric |
| Add a new MCP tool | `lib/aurora/mcp/server.py::list_tools` and `_dispatch` |
| Override the model for one agent | `.env::AURORA_MODEL_<AGENT>=<model>` or `policy.yaml::routing.bindings.<agent>` |

## Boundary conditions

- **Token budget exhausted.** Conductor pauses Discovery and Strategist; Operate keeps running (production safety > speculative work).
- **Sentry can't reach Orchestrator.** Backs off exponentially; emits `kind: sentry_self_error`. Surgeon never auto-acts on Sentry self-errors.
- **A skill PR fails CI.** `aurora-policy validate --strict` is part of CI; bad skills can't merge.
- **Compost loops on the same pattern.** The compost rule "no open PR with the same compost-key in last 14 days" prevents this.
- **Action Center down.** All HITL gates pause. Surgeon never auto-fixes past the `max_workflows_touched_without_hitl` threshold; if Action Center is unavailable for that, the fix waits. Better stuck than wrong.

## Attribution

Built on UiPath's official `uipath-python` SDK, `UiPath/skills` skill catalog, and `uipath` CLI. Pattern inspirations (none of their code is reused — only the patterns):

- **Obra Superpowers** — TDD red/green-refactor; parallel sub-agent dispatch via worktrees
- **Matt Pocock skills** — small, sharp, single-purpose primitives; planning before code
- **Ouroboros (Q00/ouroboros)** — Socratic interview, ambiguity scoring, immutable seed
- **Factory.ai Missions** — separation-of-concerns at the architecture level

Reference-only inspirations not reused: `marcelocruzrpa/uipath-ai-skills` (XAML quality patterns), `mlbrilliance/Autonomous-RPA-Architect` (PDD-to-scaffold flow shape).
