#!/usr/bin/env bash
# AURORA hook: UserPromptSubmit
# Detect risk keywords in the user's prompt and pre-load the HITL gate.
#
# When a user prompt mentions "deploy to prod", "publish to production",
# "delete", "drop", or similar, this hook:
#   1. Logs the intent
#   2. Emits an additionalContext payload reminding the agent that this is
#      gate-bound and must route through Concierge -> Action Center
#   3. Does NOT block the prompt — agents handle the gate per policy.yaml.
#      The hook just makes sure the policy is on top of the agent's mind.
#
# Exit 0 always.

set -euo pipefail

AURORA_HOME="${AURORA_HOME:-/opt/aurora}"
LOG="${AURORA_HOME}/hooks.log"
mkdir -p "${AURORA_HOME}"

EVENT="$(cat || true)"
PROMPT="$(echo "${EVENT}" | jq -r '.prompt // .user_message // ""' 2>/dev/null || echo "")"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

[[ -z "${PROMPT}" ]] && exit 0

# Risk keywords (case-insensitive)
RISK_PATTERN='(deploy.*prod|publish.*production|delete.*process|drop.*queue|rm[[:space:]]+-rf|force[[:space:]]+push|rollback.*prod|deprecat|wipe|truncate)'

if echo "${PROMPT}" | grep -iEq "${RISK_PATTERN}"; then
    echo "[${TS}] user-prompt: risk-keyword detected, gate reminder injected" >> "${LOG}"
    cat <<'EOF'
{
  "additionalContext": {
    "aurora_gate_reminder": "Your prompt contains a risk keyword (publish to prod, delete, deprecate, force push). The matching gate in policy.yaml::gates is non-negotiable: route the action through `concierge` -> Action Center catalog `aurora_supply_chain_approvals`. Do not bypass even if the action seems obvious. Do not run destructive commands directly."
  }
}
EOF
fi

exit 0
