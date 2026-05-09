---
name: aurora-policy
description: Validate `policy.yaml` against `policy.schema.json`, expand env-var references, and run a policy dry-run that simulates how Conductor would behave on the current backlog without dispatching anything. Used at boot, before every Conductor schedule, and on-demand via `aurora policy validate` / `aurora policy dry-run`. Hard fails if the policy is invalid; soft warnings for sub-optimal configurations (low test coverage floor, missing emergency_patch gate, etc.).
---

# aurora-policy

The policy is the contract between the human and the swarm. If it's broken, AURORA refuses to boot. If it's risky, AURORA warns. The dry-run mode lets you see what would happen without doing it — useful before a major change.

## When to invoke

- On `aurora start` — Conductor refuses to boot if policy is invalid
- Before every Conductor schedule call — re-validate (cheap), reload if mtime changed
- Manually via `aurora policy validate` and `aurora policy dry-run`
- After any human edit to `policy.yaml` — CI invokes via `aurora policy validate --strict`

## What it checks

### Hard validation (errors block)

1. **JSON Schema conformance** to `policy.schema.json`
2. **Env-var resolution** — every `${VAR}` reference must resolve from `.env` or process env
3. **Identity sanity** — `uipath_folder` exists in Orchestrator (live check via SDK if `--live` flag), `action_catalog` exists, `github_org` is reachable
4. **Routing bindings** — every agent in `agents/` has a binding; no extra bindings for non-existent agents
5. **Gate names** — unique within the policy; only canonical kinds (interview, prod_publish, emergency_patch, deprecation, large_fix, skill_compost_pr, custom)
6. **Worktree path writability** — `worktree_root` is a writable directory

### Soft validation (warnings — don't block)

1. **Test coverage floor < 0.7** — too lenient
2. **No `emergency_patch` gate defined** — production fixes go straight in?
3. **`prod.auto: true`** — uncommon and probably wrong
4. **`surgeon.max_auto_fixes_per_day > 20`** — high autonomy, ensure HITL gates compensate
5. **Discovery sources empty** — Discovery fleet has nothing to listen to
6. **`budget.daily_usd < 5`** — likely too low, swarm will pause non-critical fleets often
7. **`skill_compost_pr.auto_merge: true`** — POLICY-FORCED to false; warn loudly and override

## How to invoke

```bash
aurora policy validate              # exit 0 = valid, 1 = invalid
aurora policy validate --strict     # warnings also exit non-zero
aurora policy validate --live       # also probes Orchestrator + GitHub for identity sanity

aurora policy dry-run               # simulate Conductor's next 24h on current backlog
aurora policy dry-run --since 7d    # replay the last week's backlog through the current policy
```

Implementation lives at `scripts/validate_policy.py` (this skill ships it) and `lib/aurora/policy.py` (loader + dry-run).

## Dry-run output

```
aurora-policy dry-run — 2026-05-09T14:00 (24h forecast)

Backlog state:
  - 3 candidates pending-analyst
  - 1 candidate ready-for-architect (CAND-…)
  - 0 candidates ready-for-deploy
  - 7 deployed bots

Conductor would dispatch:
  ✓ analyst on 3 candidates  (≈ 6m total at sonnet tier)
  ✓ architect on CAND-…       (≈ 2m at opus tier)
  ✓ forger sub-fleet on CAND-… (≈ 12m parallel at sonnet tier)
  ✓ tester on CAND-…           (≈ 4m + Test Manager publish)
  ⚠ HITL gate prod_publish — would block waiting for approver

Token budget projection:
  Spend: $4.30 of $50.00 daily cap (8.6%)
  Within budget.

Operate fleet:
  Sentry would poll 7 deployed bots every 30s — 84 polls/hr
  Auditor's daily drift check at 02:00 UTC — clean expected
  Strategist's nightly review at 02:30 UTC — no recommendations expected
```

## Anti-patterns

- Don't skip validation in CI. A bad policy that ships causes silent misroutes.
- Don't `--live` in CI from a build agent. The live probe needs Orchestrator credentials and is slow.
- Don't promote unvalidated policy to prod. CI's `validate --strict --live` is the gate.
- Don't catch and continue on validation errors. If invalid, exit non-zero and don't boot the swarm.
