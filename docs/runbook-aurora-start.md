# Runbook — `aurora start` 5-minute live verification (T-F3)

This runbook is the **manual** half of T-F3. The **offline-verifiable** half
is in `tests/unit/test_aurora_start_boot.py`, which `make ci` already runs.

The offline tests prove:
- `aurora start --skip-daemons` boots cleanly (policy load, conductor
  registry).
- `Conductor` constructs with the demo policy and registers all three
  nightly crons (auditor / strategist / compost).
- Every `agents/<name>.md` `model_tier` resolves to a valid
  `policy.yaml::routing.bindings` key.
- `Sentry` constructs without phoning home (no eager network on
  `__init__`).

This runbook covers what those tests **can't** prove without a live
UiPath tenant: the 5-minute daemon loop with no `ERROR` log entries.

## Pre-flight (one-time per environment)

1. Confirm `.env` is fully provisioned:
   - `UIPATH_URL`, `UIPATH_CLIENT_ID`, `UIPATH_CLIENT_SECRET` — External
     Application credentials minted in Automation Cloud.
   - `UIPATH_FOLDER` — exists in Orchestrator (default `AURORA-Demo`).
   - `UIPATH_ACTION_CATALOG` — pre-created Action Center catalog.
   - `GITHUB_ORG` — exists, with the demo repos under it.
   - `GITHUB_TOKEN` — fine-grained PAT with the documented scopes.
2. Run `aurora policy validate --strict --live` and confirm `3/3 ok`. If
   any probe fails, **fix it before continuing** — the daemons will
   crash on the same call within seconds of `aurora start`.

## The 5-minute live verification

```bash
# Source .env so all the ${VAR} references in policy.yaml expand.
set -a; . ./.env; set +a

# Mint an initial token. Subsequent refreshes happen inside the loop.
.venv/bin/aurora-auth mint > /dev/null   # or: python -m aurora.auth

# Tail the events stream in another terminal:
#   tail -f $AURORA_HOME/events.jsonl
# And the hook log:
#   tail -f $AURORA_HOME/hooks.log

# Start the swarm. This call blocks until SIGINT.
timeout --foreground 305 .venv/bin/aurora start 2>&1 | tee /tmp/aurora-5min.log
echo "exit=$?"   # expect 124 (timeout fired) — that means it ran the full 5 min
```

### Acceptance

After `timeout` exits:

```bash
# Boot stages must all be present:
grep -E '\[aurora\] (loading policy|policy: valid|minting UiPath token|uipath token: minted|starting conductor daemon)' /tmp/aurora-5min.log

# Sentry must have logged at least one tick:
grep 'sentry: starting' /tmp/aurora-5min.log

# No ERROR-level entries from any module:
! grep -iE '(^|\s)ERROR(\s|:)' /tmp/aurora-5min.log
```

The last `!` inverts the exit code — if the grep finds an ERROR, the line
fails the runbook. A clean run prints nothing.

### What an ERROR-level entry would mean

- `ERROR aurora.auth`: token mint failed mid-loop (refresh token expired,
  scope drift, or tenant down). Re-run `aurora policy validate --live`.
- `ERROR aurora.sentry`: SDK call into Orchestrator failed and was not
  caught. Treat as a Sentry-self-error event in events.jsonl; investigate
  via `aurora-fingerprint` cluster.
- `ERROR aurora.conductor`: a cron-dispatched coroutine raised. The
  `_safe` wrapper catches and logs; non-fatal but worth investigating.

## What "5 minutes clean" actually proves

- The cron registry runs at least one scheduled tick (Sentry polls every
  `AURORA_SENTRY_INTERVAL` seconds; the auditor / strategist / compost
  crons fire only at their scheduled hour, so most 5-min windows will not
  trigger them).
- The Sentry → events.jsonl path is alive and writes events.
- No latent bug surfaces in the boot path.
- Token refresh works at least once (the default token TTL is well over
  5 min, so this might not be exercised; for full token-refresh
  verification, run for ≥ 25 min).

## Promoting from "boot OK" to "demo-ready"

T-F4 (live Maestro instance run through the High path) is the next gate.
Don't promote past T-F3 if any of:

- A `Sentry-self-error` event lands in events.jsonl during the 5-min
  window.
- The policy validator emits a strict-mode warning that wasn't there
  before.
- Any agent's prompt body fails the Reviewer-style lint
  (`tests/agents/test_all_agents_lint.py` — T-G4).
