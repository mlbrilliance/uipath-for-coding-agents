---
name: aurora-recall
description: Read scoped slices of AURORA's three-tier memory (project, org, skill). Used by every agent at the start of a task to load only the context relevant to its work — never the whole memory blob. Backed by SQLite for fingerprints and plain Markdown for narrative memory; access is gated by scope tags so a Build agent can't accidentally pull Operate-fleet failure traces, etc. Reading is the only public interface; writing is via `aurora-fingerprint` (clusters) or direct file I/O within an agent's own scope.
---

# aurora-recall

Memory is what lets the swarm get smarter over time without each agent dragging the whole history into context. The retrieval rules are:

1. **Scoped by tier** — project, org, or skill.
2. **Scoped by fleet** — Build agents see Build patterns; Operate agents see Operate patterns. Cross-fleet reads require explicit `scope=cross` and a justification logged.
3. **Bounded** — return at most N items by default (10), ranked by recency × relevance.
4. **Read-only** — this skill never writes.

## Storage layout (recap)

- **Project memory** — `.aurora/projects/<id>/` — Markdown files (PDD, ADR, review, tester-coverage, triage notes)
- **Org memory** — `.aurora/org/` — Markdown files (vendor-quirks.md, naming-prefs.md, patterns-that-worked.md, patterns-that-failed.md)
- **Skill memory** — `.aurora/learnings/<YYYY-MM-DD>.jsonl` — one append-only line per agent learning, plus the SQLite fingerprint index

## How to invoke

```bash
# Project tier — load PDD + ADR for the current candidate
aurora recall project --candidate CAND-… --include pdd,adr

# Org tier — semantic search
aurora recall org --query "SharePoint folder rename selector recovery" --limit 5

# Skill tier — pull last N days of learnings filtered by skill
aurora recall skill --skill aurora-fingerprint --since 7d
```

In Python:

```python
from aurora.recall import recall

ctx = recall(tier="org", query="GitHub token rotation", fleet="operate", limit=5)
# returns list of {path, snippet, score, ts}
```

## What each agent should pull

| Agent | Default recall |
|---|---|
| `scout` | none — Scout doesn't reason from history |
| `curator` | org/dedup signatures |
| `analyst` | org/scoring-priors-for-similar-PDDs |
| `interviewer` | org/successful-interview-questions |
| `strategist` | org + skill (90 days), all fleets |
| `architect` | org/patterns-that-worked, project/PDD |
| `cartographer` | org/vendor-selector-quirks, project/PDD |
| `forger-*` | skill/skill-specific-learnings, project/PDD + ADR |
| `reviewer` | org/anti-patterns, project/ADR |
| `tester` | org/test-patterns, project/PDD |
| `sentry` | none — Sentry observes, doesn't reason |
| `diagnostician` | skill/fingerprints (cluster lookup), org/known-environment-issues |
| `surgeon` | project/triage, skill/prior-resolutions-for-cluster |
| `auditor` | org/governance-rules, project/deploy-history |
| `concierge` | none — Concierge ferries; doesn't reason |
| `conductor` | full read of policy + budget + worktree state |

## Ranking algorithm

For each candidate item:
- **recency**: exponential decay with half-life 30 days
- **relevance**: cosine similarity over a TF-IDF sketch of the item's text against the query (or the agent's task context if no explicit query)
- **scope match**: items tagged with the calling fleet score 1.0; cross-fleet items 0.5
- **resolved bonus**: items with `resolution_pr` set in the fingerprint index get +0.2

Rank = 0.5 × recency + 0.3 × relevance + 0.15 × scope + 0.05 × resolved bonus

## Anti-patterns

- Don't `cat` the memory directory directly — always go through this skill so scoping is enforced.
- Don't ask for `cross` scope without a documented reason. Conductor logs cross-scope reads for audit.
- Don't pull more than `limit` items; if the agent needs more, narrow the query.
- Don't cache results across invocations — memory updates frequently and a stale cache hides recent learnings.
