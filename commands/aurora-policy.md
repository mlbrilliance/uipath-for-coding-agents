---
description: Validate `policy.yaml` and run policy-shape dry-runs. Hard fails on schema errors or unresolved env vars; warns on risky configurations. Dry-run shows what Conductor would do over the next N hours given the current backlog and Operate-fleet state, without dispatching anything.
argument-hint: validate [--strict] [--live] | dry-run [--since <duration>] | reload
---

# /aurora-policy

Inspect AURORA's operating policy.

## Subcommands

### `validate`

```
/aurora-policy validate [--strict] [--live]
```

Runs `skills/aurora-policy/scripts/validate_policy.py`. Hard-fails on:
- JSON Schema violation against `policy.schema.json`
- Unresolved `${VAR}` references (env not loaded or missing)
- Duplicate gate names
- Routing bindings for non-existent agents

Soft-warns on (don't block unless `--strict`):
- `build.test_coverage_floor < 0.7`
- `deploy.prod.auto: true`
- Missing `emergency_patch` gate
- `surgeon.max_auto_fixes_per_day > 20`
- Empty `discovery.sources`
- `budget.daily_usd < 5`

`--live` adds external probes:
- Confirm `identity.uipath_folder` exists in Orchestrator
- Confirm `identity.action_catalog` exists in that folder
- Confirm `identity.github_org` is reachable with `GITHUB_TOKEN`

### `dry-run`

```
/aurora-policy dry-run [--since <duration>]
```

Replays the current backlog and Operate-fleet state through the *current* policy without dispatching. Useful before promoting a policy change. Output:

- What Conductor would dispatch (and to which fleet)
- Estimated token spend per agent + total
- Which HITL gates would fire
- Whether budget is enough

`--since 7d` replays the last 7 days of decisions through the new policy; lets you see how a policy change would have changed past behavior. Exits 0 if outcomes match within tolerance, 1 if material divergence.

### `reload`

```
/aurora-policy reload
```

Force the running Conductor daemon to reload `policy.yaml` without restarting. Use after a small edit; for big edits, prefer `aurora restart`.

## Failure modes

- **`unresolved env var: UIPATH_CLIENT_SECRET`** — `.env` is missing the var, or env was not sourced. Check with `env | grep UIPATH`.
- **`error at /gates/2/trigger: 'foo' is not of type 'string'`** — schema mismatch; the validator's path tells you which gate.
- **`duplicate gate name: prod_publish`** — combine the duplicate gates or rename one.

## Related

- `policy.yaml` — the policy itself
- `policy.schema.json` — the schema
- `/aurora-status` — see what's actually happening
