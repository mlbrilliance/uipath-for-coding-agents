---
description: Open AURORA's TUI dashboard. Shows live state of all 19 agents, the backlog, recent runs, current HITL gates pending, token-budget consumption, and Operate-fleet event stream. Read-only.
argument-hint: [--once] [--filter fleet=discovery|build|operate]
---

# /aurora-status

Live dashboard for the swarm.

## What you see

A four-pane Textual TUI:

- **Top-left — agents**: all 19, color-coded by state (idle / dispatched / active / blocked / paused). Token spend per agent today.
- **Top-right — backlog**: the candidate pipeline. Pending → analyst-scoring → ready-for-architect → forging → testing → deploying → operating. Counts per stage.
- **Bottom-left — events**: the last N events from `events.jsonl` (Sentry's stream). Live-updating tail.
- **Bottom-right — gates**: any open HITL Action Center tasks with elapsed time, approver, and timeout countdown.

## Keys

| Key | Action |
|---|---|
| `q` | quit (daemons keep running) |
| `r` | refresh now |
| `f` | filter by fleet (cycle: all / discovery / build / operate) |
| `g` | jump to gates pane |
| `e` | jump to events pane (live tail) |
| `b` | jump to backlog pane |
| `?` | help overlay |

## Inputs

- `--once` — render once and exit (for `watch -n 5 aurora status --once` or scripting)
- `--filter fleet=<name>` — show only one fleet's agents

## Output (with `--once`)

```
AURORA — uipath-for-coding-agents · 2026-05-09T14:23:00Z
─────────────────────────────────────────────────────────
Agents (19)        ┃ Backlog                ┃ Gates open: 1
  Discovery (5)    ┃                        ┃   prod_publish (CAND-…)
    scout      ●   ┃   pending-analyst    3 ┃   created  37m ago
    curator    ●   ┃   ready-for-arch.    1 ┃   approver puneet@…
    analyst    ◐   ┃   forging             1 ┃   timeout  in 7h 23m
    interview. ○   ┃   testing            0 ┃ ─────────────────────
    strategist ○   ┃   deploying          0 ┃ Token budget today
                   ┃   operating         12 ┃   Spent: $4.30 / $50
  Build (8)        ┃                        ┃   Discovery $0.40
    architect  ●   ┃ Last runs              ┃   Build     $3.10
    cartograph.◐   ┃   2026-05-09T14:11   ✓ ┃   Operate   $0.80
    forger-rpa ●   ┃   2026-05-09T13:42   ✓ ┃ ─────────────────────
    forger-cd  ◐   ┃   2026-05-09T03:42   ⚠ ┃ Operate-fleet events
    forger-ag  ○   ┃                        ┃ (last 5)
    forger-mst ●   ┃ Recent compost         ┃   14:23 sentry  ok
    reviewer   ○   ┃   1 PR open            ┃   14:22 sentry  ok
    tester     ○   ┃   2 watching           ┃   14:21 sentry  job_failed
                   ┃                        ┃   ...
  Operate (5)      ┃                        ┃
    sentry     ●   ┃                        ┃
    diagnost.  ◐   ┃                        ┃
    surgeon    ●   ┃                        ┃
    auditor    ○   ┃                        ┃
    concierge  ○   ┃                        ┃
─────────────────────────────────────────────────────────
●=active ◐=in-progress ○=idle ⏸=paused ⚠=warn
```

## Don't use this command

- For scripting/automation — use `aurora status --once` and parse the JSON via `aurora status --json`. The TUI is for humans.

## Related

- `/aurora-recall` — search swarm memory
- `/aurora-policy` — see what the policy would do
