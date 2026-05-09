---
description: Capture the current AURORA session context and route it to UiPath's feedback channel. Mirrors UiPath/skills' built-in `/uipath-feedback` but with AURORA-specific context (agent fleet state, recent dispatches, last fault). No screenshots, no repro steps required — the swarm's own runs and learnings provide context.
argument-hint: [--include events|backlog|gates|all] [--note "<one-line note>"]
---

# /aurora-feedback

When something in AURORA broke and you want to tell us.

## What gets sent

By default:
- The last 10 events from `events.jsonl`
- The current backlog state
- Open HITL gates and their elapsed times
- The last 5 Conductor runs from `.aurora/runs/`
- The last 20 lines of `hooks.log`

Plus an optional one-line note from `--note`.

What's NOT sent (ever):
- `.env` contents
- UiPath access tokens
- GitHub PAT
- Slack tokens
- Action Center form payloads (may contain sensitive context)
- File contents from worktrees (these may contain proprietary code)

The bundle is sanitized via `lib/aurora/feedback.py`'s redaction layer before send.

## Inputs

- `--include` — choose what to bundle. Default `all`. Options: `events`, `backlog`, `gates`, `runs`, `logs`, `all`.
- `--note "..."` — a one-line note (≤ 200 chars).

## How

```
/aurora-feedback --note "Surgeon opens a PR but never moves to verifying CI"
```

Output:

```
[aurora-feedback] bundling 8 events, 4 backlog items, 1 open gate, 5 runs, 20 log lines
[aurora-feedback] redacting: 0 secrets matched, 0 file paths anonymized
[aurora-feedback] uploading to https://forum.uipath.com/feedback/intake (anonymized session id: aurora-2026-05-09-abc123)
[aurora-feedback] uploaded; reply will arrive at puneetsatyawan@gmail.com if registered
```

## Don't use this command

- To report a security issue. Use UiPath's responsible disclosure channel directly.
- To send a feature request. Use the [UiPath community forum](https://forum.uipath.com/) — feedback is for bugs in the agent or skill behavior.

## Related

- `UiPath/skills` ships `/uipath-feedback` — that's for issues with the official skills. Use it when the problem is in `uipath-rpa-workflows` etc., not in AURORA's wrappers.
