---
description: Search AURORA's three-tier memory. Project tier (per-bot artifacts), org tier (cumulative patterns and quirks), skill tier (one-line learnings and the fingerprint index). Returns ranked excerpts with paths so you can drill in. The same retrieval the agents use internally — visible to the human.
argument-hint: <query> [--tier project|org|skill] [--fleet discovery|build|operate] [--limit N] [--since <duration>]
---

# /aurora-recall

Search the swarm's memory.

## Examples

```
/aurora-recall SharePoint folder rename
/aurora-recall token rotation --tier skill
/aurora-recall vuln-lookup --tier project --fleet build
/aurora-recall "what did we learn about NVD rate limits last week?" --since 7d
```

## How it ranks

For each candidate item:
- **recency**: exponential decay with 30-day half-life
- **relevance**: cosine similarity over a TF-IDF sketch of the item's text against the query
- **scope match**: items tagged with the requested fleet score 1.0; cross-fleet 0.5
- **resolved bonus**: items linked to a Surgeon resolution PR get +0.2

Rank = 0.5 × recency + 0.3 × relevance + 0.15 × scope + 0.05 × resolved.

## Output

```
[aurora-recall] query="SharePoint folder rename" tier=any limit=10 elapsed=42ms

★★★★★  .aurora/learnings/2026-05-08.jsonl#aabbccdd
        agent=surgeon  cluster=selector-broken/wnd-aaname-mismatch
        "SharePoint folder rename resolved by re-walking parent ariaName chain.
         Cluster size 12, all auto-fixed. Fingerprint: aabbccdd."
        12 prior occurrences across 4 projects.

★★★★☆  .aurora/org/vendor-selector-quirks.md#sharepoint
        "SharePoint Modern UI renames folders without changing IDs;
         the 'aaname' attribute changes but the parent's role tree
         stays stable. Always include parent walk in selector fallback set."

★★★☆☆  .aurora/projects/CAND-2026-04-12-ee01abcd/triage/2026-04-15T03:11.md
        Older but exact-fingerprint match. Resolution PR: #18.

(7 more items elided; use --limit 20 to see all)
```

## Inputs

- `<query>` (positional, required) — natural-language search string
- `--tier project|org|skill|any` — restrict to one tier; default `any`
- `--fleet discovery|build|operate` — restrict to one fleet's scope
- `--limit N` — default 10
- `--since 7d|30d|90d` — only return items younger than the duration
- `--candidate CAND-…` — restrict to one project

## Don't use this command

- To dump all memory. There's no `--all` flag intentionally; if you want to inspect raw memory, `cat` the relevant directory directly. Recall enforces scoping.

## Related

- `/aurora-status` — see what's actively in flight
- `/aurora-feedback` — when memory tells you something is broken
