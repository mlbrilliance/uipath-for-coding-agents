---
name: aurora-fingerprint
description: Cluster failure events by structural fingerprint and append to memory. Used by Diagnostician and Surgeon. A fingerprint is `<top-level-kind>/<refinement>` plus locality (workflow file or agent name). Clustering uses kNN over a structured-feature embedding stored in SQLite. Output is a cluster ID and confidence score; downstream agents use these to decide auto-fix vs HITL.
---

# aurora-fingerprint

Failures repeat. The first time SharePoint renames a folder, the swarm sees a novel `SelectorNotFoundException`. The fifth time, that same exception clusters with prior occurrences — and Surgeon's prior remediation is reusable.

This skill does the clustering. It writes one record per fault to a SQLite index, indexes it for similarity search, and on subsequent calls returns the matching cluster (or `novel` if no match).

## When to invoke

- After Sentry emits any `kind: *_failed` or `kind: *_faulted` event — Diagnostician calls this skill first
- When Surgeon completes a fix — write the resolution back so future occurrences inherit the prior remediation

## Storage

- **Fingerprint index**: `${AURORA_HOME}/fingerprints.db` — SQLite, schema:

  ```sql
  CREATE TABLE fingerprints (
    id TEXT PRIMARY KEY,                  -- sha256 of structural features
    cluster_id TEXT NOT NULL,             -- short stable id
    kind TEXT NOT NULL,                   -- selector-broken, auth-failed, ...
    refinement TEXT,                      -- wnd-aaname-mismatch, token-expired, ...
    locality TEXT,                        -- Workflows/GitHub/FetchLockfile.xaml
    exception_type TEXT,
    exception_message TEXT,
    project_id TEXT,
    first_seen TEXT,
    last_seen TEXT,
    occurrences INTEGER DEFAULT 1,
    resolution_pr TEXT,                   -- gh PR url if Surgeon resolved
    resolution_summary TEXT
  );
  CREATE INDEX idx_cluster ON fingerprints(cluster_id);
  CREATE INDEX idx_kind ON fingerprints(kind);
  ```

- **Append-only learnings JSONL**: `${AURORA_HOME}/learnings/<YYYY-MM-DD>.jsonl` — one event per line, consumed nightly by `aurora-compost`.

## How to use

```bash
python scripts/cluster.py classify --event-file <path-to-event.json>
# emits: { "cluster_id": "abc123", "novel": false, "size": 12, "confidence": 0.78,
#          "prior_resolution": { "pr": "...", "summary": "..." } }

python scripts/cluster.py append --resolution --cluster <id> --pr <url> --summary "..."
# updates the cluster row with Surgeon's resolution

python scripts/cluster.py list --kind selector-broken --limit 20
# debug
```

## Clustering features (the embedding)

A fingerprint is computed deterministically from these structural fields, NOT from the raw exception message text alone:

1. `kind` — top-level taxonomy (8 values; see below)
2. `refinement` — second-level taxonomy
3. `locality` — workflow file or agent name (normalized to a project-relative path)
4. `exception_type` — fully-qualified class name (e.g., `UiPath.Core.Activities.SelectorNotFoundException`)
5. `message_skeleton` — exception message with selectors, paths, IDs replaced by `<token>`. Example: `"Could not find selector <selector> after <duration>ms"`.

The kNN compares structural features by exact match for `kind`+`refinement`+`exception_type`, weighted edit distance for `locality`, and shingle overlap for `message_skeleton`. No LLM-based similarity — keep it deterministic, fast, cheap.

## Top-level kinds (canonical taxonomy)

- `selector-broken` — UI selector failed to find or matched > 1
- `auth-failed` — 401/403 from any external API or UiPath Identity
- `external-api-drift` — 4xx or 5xx from a previously-working API; schema change suspected
- `null-arg` — null reference / missing argument
- `timing` — timeout (UI, HTTP, queue dequeue)
- `data-quality` — input shape unexpected; parser failed
- `network` — DNS / connectivity / TLS
- `license` — UiPath robot license unavailable

If you encounter a fault that doesn't fit, do NOT invent a new kind on the fly. Emit `kind: novel-fault` and let Conductor escalate. The compost step is where new kinds become canonical.

## Anti-patterns

- Don't cluster based on raw message text. Two faults with identical-looking messages but different `exception_type` are different fingerprints.
- Don't hash secrets. The `message_skeleton` step replaces tokens that look like UUIDs, paths, URLs.
- Don't store the full exception trace in SQLite. Keep the row small; trace lives at `.aurora/triage/<ts>.md`.
- Don't auto-resolve a fingerprint just because its cluster has past resolutions. Surgeon decides per-case based on confidence and policy guardrails.
