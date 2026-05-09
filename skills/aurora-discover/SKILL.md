---
name: aurora-discover
description: Extract structured friction signals from raw text sources (Slack messages, Jira issues, email digests, calendar invite notes, screen-recording transcripts). Used by `scout` to convert noisy human chatter into machine-actionable candidate signals. Returns one JSON object per signal with frequency hints, duration hints, pain indicators, and named systems. Reject one-off, internal-swarm, and metadata-only chatter.
---

# aurora-discover

Scout invokes this skill on every batch of new messages it pulls. The goal is structure: turn "every Monday I spend 2 hours pulling vendor invoices from SharePoint" into a typed candidate the rest of the swarm can act on.

## Input

A list of `{source, ts, author, raw}` records. The source is one of `slack:#channel`, `jira:PROJ`, `email:inbox`, `calendar:user@org`, `transcript:recording-id`. AURORA's source adapters live in `lib/aurora/sources/`.

## Output

For each genuine friction signal in the input, emit one JSON object:

```json
{
  "id": "scout-<sha256-of-raw-content>",
  "source": "slack:#rpa-asks",
  "ts": "2026-05-09T14:23:00Z",
  "author": "user-name",
  "raw": "every Monday I spend 2 hours pulling vendor invoices from SharePoint",
  "signal": {
    "actor": "user-name-or-role",
    "frequency_hint": "weekly | daily | quarterly | event-driven | unknown",
    "duration_hint": "2 hours",
    "pain_indicators": ["spend", "every"],
    "system_hints": ["SharePoint", "vendor invoices"],
    "candidate_action_verbs": ["pull", "extract", "consolidate"]
  }
}
```

If a record is not a friction signal, emit nothing. Don't emit "low-confidence" placeholders.

## Detection rubric

A record is a friction signal if it contains at least one item from each of two categories:

**Category A: cadence or duration**
- frequency phrases: "every Monday", "weekly", "always", "every quarter", "each time"
- duration phrases: "X hours", "all morning", "the whole day", "takes forever"
- repetition: same author + similar topic mentioned ≥ 2 times in last 30 days

**Category B: pain or manual labor**
- pain verbs: "spend", "stuck", "manually", "by hand", "copy-paste", "fight with"
- scope: ≥ 1 named system that has a public API (so it's plausibly automatable)

## What to skip

- Internal swarm chatter — anything mentioning `aurora-`, `forger-`, `concierge`
- One-off complaints with no cadence ("I had to do X today")
- Discussions of an existing automation (unless it's broken)
- Pure questions or confusion ("Does anyone know how X works?")
- Praise or acknowledgment ("Thanks for fixing X")

## Anti-patterns

- Don't propose solutions in the signal. Solutions are Architect's job.
- Don't infer the actor when the source doesn't name them. Use `unknown`.
- Don't merge multiple complaints into one signal. Curator deduplicates downstream.
- Don't normalize quotes or fix typos in `raw`. Audit trail.
