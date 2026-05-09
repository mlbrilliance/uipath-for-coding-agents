---
description: Boot the AURORA swarm. Validates policy.yaml, mints a fresh UiPath OAuth token, starts the Operate-fleet daemons (Sentry, Auditor schedule, Strategist nightly cron), opens the TUI dashboard, and begins polling the Discovery sources from policy.yaml.
argument-hint: [--skip-daemons] [--policy <path>]
---

# /aurora-start

Boot the swarm.

## What this does

1. Resolve `.env` from the current working directory or up to 5 parents.
2. Run `aurora policy validate` (the `aurora-policy` skill). Refuse to boot on errors.
3. Run `aurora-auth/scripts/mint_token.py` with the full scope set from `policy.yaml::uipath_scopes`. Writes `UIPATH_ACCESS_TOKEN` to `.env` and the sidecar at `~/.uipath/aurora-token.json`.
4. Spawn the Conductor as the parent agent for this session. Conductor reads `policy.yaml` and the current backlog.
5. (Unless `--skip-daemons`) start the Operate-fleet daemons via `lib/aurora/conductor.py daemon`:
   - Sentry — Orchestrator polling at `policy.operate.sentry.poll_interval_seconds`
   - Auditor — daily drift check at 02:00 UTC
   - Strategist — nightly retrospective at 02:30 UTC
   - Compost step — at 03:00 UTC
6. Open the TUI dashboard at `aurora status` (read-only view; use Ctrl-C to exit, daemons keep running).

## Use this command

- The first time you set up AURORA on the VPS
- After any change to `policy.yaml`
- After Anthropic OAuth re-auth (`claude login`)
- After UiPath credential rotation

## Don't use this command

- To "restart" — daemons survive Claude Code session restarts via systemd. Use `aurora restart` for that.
- In CI — CI runs `aurora policy validate --strict --live`, not the full boot.

## Inputs

- `--skip-daemons` — boot Conductor and validate, but don't spawn the long-running Operate-fleet processes. Useful for read-only inspection.
- `--policy <path>` — use a non-default policy file (e.g., `policy.test.yaml`). Default: `./policy.yaml`.

## Output

After successful boot:

```
[aurora] policy: valid (1 warning)
[aurora] uipath token: minted, expires in 3600s, scopes: 15
[aurora] conductor: ready
[aurora] sentry daemon: started (pid 4123, polling AURORA-Demo every 30s)
[aurora] auditor cron: scheduled
[aurora] strategist cron: scheduled
[aurora] compost cron: scheduled
[aurora] dashboard: opened
```

## Failure modes

- **Policy invalid** — see the validator error; fix `policy.yaml` and rerun
- **Token mint failed** — check `.env` for `UIPATH_CLIENT_ID` / `UIPATH_CLIENT_SECRET`; re-run the curl test from `CLAUDE.md`
- **Daemons already running** — `aurora-start` refuses; use `aurora restart` to recycle

## Related

- `/aurora-status` — dashboard
- `/aurora-policy` — validate or dry-run policy
- `/aurora-feedback` — send a session report to UiPath
