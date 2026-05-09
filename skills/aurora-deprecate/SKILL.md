---
name: aurora-deprecate
description: Retire an unused or superseded UiPath process safely. Used by Strategist + Auditor + Concierge in sequence: Strategist proposes, Auditor checks dependencies, Concierge gates via Action Center, then this skill executes the deprecation steps. Stops scheduled triggers, archives the package, transfers any in-flight queue items to a successor (if any), updates org memory's deprecation log, and writes a runbook so the retired process can be restored within 30 days if needed.
---

# aurora-deprecate

Retiring a bot is irreversible-feeling but should be reversible-in-practice. AURORA's deprecation flow is conservative: stop, don't delete; archive, don't destroy; document, don't assume.

## When to invoke

- After Strategist's recommendation passes Auditor's cross-folder dependency check
- After Concierge's HITL gate (`kind: deprecation`) is approved
- Never on its own — always part of the Strategist → Auditor → Concierge → Deprecate chain

## Pre-flight checks (re-run even if Auditor passed earlier)

1. **No in-flight jobs.** Stop if `sdk.jobs.list(state="Running", process=...)` is non-empty. Wait or escalate.
2. **No queue items in `New` or `InProgress`** for queues this process owns. If yes, document and either drain or transfer.
3. **No active Maestro instances** referencing the process as a task implementation.
4. **No other deployed package** invokes this one as a child via `uipath:taskBinding`.
5. **No active triggers (schedules, queue triggers, message triggers).** Disable all before proceeding.

If any pre-flight fails, abort and write `.aurora/deprecation/<process>-blocked-<ts>.md` describing the blocker.

## Execution steps (in order; reversible)

1. **Disable triggers** via the SDK (`sdk.processes.update(state="Disabled")` or similar).
2. **Take a final snapshot** of the package, its bindings, and last 90 days of execution metrics. Write to `.aurora/archive/<process>/<ts>/`.
3. **Move the package to an archive folder** in Orchestrator named `<UIPATH_FOLDER>-Archive` (created on first deprecation; reusable). Keeps the package available for restore but out of normal scope.
4. **Update org memory** — append to `.aurora/org/deprecation-log.md`:
   ```markdown
   ## <ProcessName> — deprecated 2026-05-09
   - Reason: 0 successful runs in 90 days, last modified 2024-11
   - Successor: <if any>
   - Approver: puneet@example.com (Action Center task abc-123)
   - Archive location: ${UIPATH_FOLDER}-Archive/<ProcessName>@<version>
   - Restore window: 30 days (until 2026-06-08)
   - Restore command: `aurora deprecate restore --process <name> --version <v>`
   ```
5. **Write a restore runbook** at `.aurora/archive/<process>/<ts>/restore.md` — concrete commands to bring the bot back, plus what would need to change (re-enable triggers, re-attach to its old folder, etc.).
6. **Notify owners** — Concierge sends an Action Center notice to the process's prior owners (read from package metadata).
7. **Schedule the final purge** — if the process isn't restored within 30 days, the next compost-step archive cleanup will remove the binary (org memory and runbook stay forever).

## Restore (within 30 days)

```bash
aurora deprecate restore --process <ProcessName> --version <v>
```

This re-publishes the archived package back into `${UIPATH_FOLDER}`, re-enables disabled triggers (with explicit confirmation per trigger), and updates org memory.

## Anti-patterns

- Don't delete packages. Always archive.
- Don't silently transfer queue items. If a successor exists, route through Concierge for explicit approval — queue-item ownership is a contract.
- Don't deprecate during business hours without HITL approval already in hand. Deprecation is "irreversible feeling" even when reversible.
- Don't deprecate the same process twice in a quarter. If you bring it back, give it a quarter to prove out before re-retiring.
- Don't skip the restore runbook step. Future-you will need it.
