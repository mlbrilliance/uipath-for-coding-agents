---
name: aurora-replay
description: Replay a faulted Maestro instance (or standalone job) in a sandbox folder using the same input data, to isolate whether the root cause is in the bot, the environment, or an external dependency. Used by Diagnostician for non-trivial faults (cluster overlap < 0.6 or external dependency suspected). The "Shadow twin" pattern from AURORA's design.
---

# aurora-replay

When a production bot fails, the obvious question is: was it the code, the data, or the world? Reading the exception trace alone often can't tell you. Replay does: spin up the same package, in a sandbox folder, with the same input, and observe what happens.

## When to invoke

Diagnostician invokes this skill when fingerprint-based clustering returns a confidence < 0.6, OR when the suspected kind is `external-api-drift`, OR when the same fingerprint has been "fixed" recently and is recurring (suggesting the prior fix targeted the wrong layer).

## How it works

1. **Resolve the failed instance.** Given a Maestro `instance_id` or job `id`, fetch:
   - The package version that was running
   - The input variables / arguments
   - The folder it ran in
   - For Maestro: the path it took up to the fault, and the values of process variables at the fault point

2. **Provision a sandbox.** Either:
   - Use a pre-existing sandbox Orchestrator folder named `${UIPATH_FOLDER}-Sandbox` (recommended; created once per tenant)
   - Or create one on demand via `uipath-platform` skill

3. **Republish the failed package version into the sandbox** with the same execution identity. (The sandbox's identity must NOT have permission to mutate any external system the bot writes to — replay should be safe by design. Concierge sets up sandbox identities at first run with read-only credentials where possible.)

4. **Trigger a job in the sandbox** with the same input. For Maestro, start a fresh instance with the same input variables.

5. **Observe.** Wait up to N seconds (default 300) for completion or fault. Capture:
   - Did it fault at the same step? (→ root cause likely in the bot)
   - Did it fault at a different step? (→ data or environment-specific)
   - Did it succeed? (→ root cause was external; the fault was transient or environment-side)
   - For Maestro: where did the path diverge from prod's traced execution?

6. **Emit a replay record** at `.aurora/triage/<event-ts>-replay.md` with the comparison. Diagnostician folds this into its hypothesis.

## Safety invariants

- **The sandbox must not write to production systems.** Concierge configures the sandbox folder's robot account with read-only or test-environment credentials at setup. AURORA never elevates privileges in a sandbox.
- **No external side effects without dry-run mode.** Bots that send Slack messages, post GitHub PRs, etc., must check an env-style `AURORA_DRY_RUN=true` flag. AURORA's coded workflows respect this; XAML workflows opt in via a Config.xlsx setting `EnableDryRun`.
- **Time-box.** Default 300s. After timeout, kill the sandbox job, mark the replay as "inconclusive: timeout."

## How to invoke

```bash
python -m aurora.replay --instance <instance-id>
python -m aurora.replay --job <job-id>
# or with explicit args
python -m aurora.replay --package <pkg> --version <v> --folder ${UIPATH_FOLDER}-Sandbox --input <json>
```

(The implementation lives in `lib/aurora/replay.py` — it wraps the `uipath-python` SDK and the Maestro instance-management API.)

## Anti-patterns

- Don't replay in the production folder. Always sandbox.
- Don't replay without the dry-run flag set when the bot has any write side-effects.
- Don't trust a single replay. If the result is ambiguous (intermittent), run twice with the same input and once with a deliberately mutated input to bisect data vs. environment.
- Don't auto-act on replay results. Diagnostician interprets, Surgeon decides.
