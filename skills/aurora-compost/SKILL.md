---
name: aurora-compost
description: Nightly self-improvement loop. Reads the day's `learnings/<date>.jsonl`, clusters them by skill/agent, identifies recurring patterns (≥ 3 occurrences across ≥ 2 projects), and opens a GitHub PR against `skills/` (or `agents/`) with a proposed update — e.g., a new fingerprint refinement, an updated SKILL.md guidance, a new helper script. The PR is HITL-gated via `aurora-promote` (kind: skill_compost_pr) and never auto-merged. The mechanism that makes the swarm get smarter with use.
---

# aurora-compost

Every agent writes one-line learnings as it works. Most are mundane. Some recur. The ones that recur, across projects, with consistent rationale — those are worth turning into a skill update. Compost is what turns the day's accumulated learnings into a versioned, reviewed change to the swarm itself.

## When to invoke

- Once nightly via the Conductor's daemon mode — typically 02:00 UTC after Auditor's daily pass
- On-demand via `aurora compost --since N --dry-run` to preview proposed PRs

## Inputs

- `${AURORA_HOME}/learnings/*.jsonl` — every agent's appended learnings, one JSON object per line:

  ```json
  {
    "ts": "2026-05-09T03:42:11Z",
    "agent": "surgeon",
    "skill": "aurora-fingerprint",
    "project_id": "CAND-2026-05-09-aabbccdd",
    "kind": "fingerprint-resolution",
    "summary": "selector-broken/wnd-aaname-mismatch resolved by re-walking parent ariaName chain",
    "context": { "...": "..." }
  }
  ```

- The fingerprint SQLite at `${AURORA_HOME}/fingerprints.db` — for cross-referencing cluster sizes
- Org memory at `.aurora/org/`

## Outputs

For each composted pattern, one GitHub PR against the swarm's own repo. PR title format:

```
Skill update: <skill-name>: <one-line rationale>
```

PR body:

```markdown
# Compost-step skill update

## Pattern observed
<rationale: what recurred, in what context, why an update is warranted>

## Evidence
- 12 occurrences across 4 projects in last 30 days
- Cluster `selector-broken/wnd-aaname-mismatch`
- All 12 resolved by Surgeon with the same remediation; 0 regressions

## Proposed change
- `skills/aurora-fingerprint/scripts/cluster.py` — add a refinement detector for the new pattern
- `skills/aurora-fingerprint/SKILL.md` — document the refinement in the canonical taxonomy table

## Risk
- Low — additive; no existing behavior modified

## Verification
- [ ] aurora-policy validate (passes)
- [ ] tests/aurora-fingerprint pass with the new fixture
- [ ] HITL approval via Action Center
```

After opening the PR, this skill calls `aurora-promote` with `kind: skill_compost_pr` to gate it. The PR is **never auto-merged** — even when CI is green and the change is trivially additive. The whole point of the gate is bounded autonomy.

## Compost rules

A learning becomes a compost candidate when ALL hold:

- **Recurrence**: ≥ 3 occurrences in the last 30 days
- **Cross-project**: ≥ 2 distinct projects (so you're not just learning a single bot's quirks)
- **Consistent rationale**: at least 70% of occurrences have similar `summary` text (TF-IDF threshold)
- **Stable resolution**: if `kind == fingerprint-resolution`, the proposed remediation worked the last 3 times in a row (no regressions)
- **Not already proposed**: no open PR with the same compost-key in the last 14 days

If only some of those hold, append the learning to a "watching" list and revisit next compost. Don't propose half-baked PRs.

## What gets composted into what

| Pattern type | Target |
|---|---|
| New fingerprint refinement | `skills/aurora-fingerprint/scripts/cluster.py` (`derive_refinement`) |
| New canonical kind | `skills/aurora-fingerprint/SKILL.md` taxonomy table |
| Updated PDD anti-pattern | `skills/aurora-pdd/templates/ambiguity-rubric.md` |
| New REFramework lint rule | `.claude/rules/aurora-conventions.md` |
| Vendor-specific selector quirk | `.aurora/org/vendor-selector-quirks.md` (org memory, not a skill) |
| New gate template | `skills/aurora-promote/templates/<kind>.json` |
| New agent role (rare) | `agents/<name>.md` — always HITL, always with explicit Conductor schedule |

## Anti-patterns

- Don't auto-merge. Even when CI is green. The whole point is HITL.
- Don't compost a single project's learnings into an org-wide skill. Cross-project evidence is required.
- Don't compost mid-day. The daily cadence ensures the day's full distribution is in scope.
- Don't compost the compost step. It changes its own rules through PRs the human reviews; it does not self-mutate via composting.
- Don't compost into `lib/aurora/*.py` core code. Code changes are PRs from humans (or `surgeon`-style fixes), not from compost. Compost only updates skills, agent definitions, rules, and org memory.

## Output

A one-line summary plus the PR list:

```
aurora-compost: 2026-05-09 — 1 PR opened (aurora-fingerprint refinement), 2 watching, 0 deferred
  - https://github.com/aurora-demo-org/uipath-for-coding-agents/pull/47
```
