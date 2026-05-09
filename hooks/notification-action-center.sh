#!/usr/bin/env bash
# AURORA hook: Notification
# Route Claude Code's notification events (HITL prompts, blocking gates,
# long-running waits) to UiPath Action Center via the Concierge agent.
#
# Claude Code emits notifications for events like "agent is waiting on
# user input." If we're inside an AURORA session, we want that to surface
# in Action Center so the human can respond from there (audit trail) instead
# of needing to be in the terminal.
#
# Exit 0 always.

set -euo pipefail

AURORA_HOME="${AURORA_HOME:-/opt/aurora}"
LOG="${AURORA_HOME}/hooks.log"
mkdir -p "${AURORA_HOME}"

EVENT="$(cat || true)"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
KIND="$(echo "${EVENT}" | jq -r '.kind // .type // "unknown"' 2>/dev/null || echo "unknown")"
MESSAGE="$(echo "${EVENT}" | jq -r '.message // .text // ""' 2>/dev/null || echo "")"

[[ -z "${MESSAGE}" ]] && exit 0

# Only route notifications that look like HITL waits — let trivial pings pass
ROUTE_PATTERN='(waiting|approval|review|confirm|gate)'

if ! echo "${MESSAGE}" | grep -iEq "${ROUTE_PATTERN}"; then
    exit 0
fi

# Defer the actual Action Center create to Concierge agent's promote skill.
# Here we just write a marker that the daemon picks up. The daemon batches
# notifications so we don't flood the catalog.
INBOX="${AURORA_HOME}/notification-inbox"
mkdir -p "${INBOX}"
FILE="${INBOX}/${TS}-$(printf '%05d' "$RANDOM").json"

jq -nc \
    --arg ts "${TS}" \
    --arg kind "${KIND}" \
    --arg msg "${MESSAGE}" \
    '{ts: $ts, kind: $kind, message: $msg, source: "claude-code-notification"}' \
    > "${FILE}"

echo "[${TS}] notification: queued for Concierge — ${FILE}" >> "${LOG}"
exit 0
