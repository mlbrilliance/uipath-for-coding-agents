#!/usr/bin/env bash
# AURORA hook: PreToolUse
# Inject scoped memory into the agent's context before any tool call.
#
# Reads the JSON-on-stdin event from Claude Code, looks up the calling
# subagent name, and emits a small JSON payload of relevant memory slices
# the agent will see prepended to its next turn.
#
# Scoping: each agent's role -> memory tier mapping lives in the agent's
# `aurora-recall` defaults table.
#
# Exit codes:
#   0  — emit context payload on stdout (Claude Code injects it)
#   1  — non-fatal error; log and continue (no injection)
#   2  — block the tool call (used only when memory is unavailable AND the
#        agent is one that strictly requires it: surgeon, diagnostician)

set -euo pipefail

AURORA_HOME="${AURORA_HOME:-${HOME}/.aurora}"
LOG="${AURORA_HOME}/hooks.log"
mkdir -p "${AURORA_HOME}"

# Read the hook event from stdin (Claude Code passes JSON)
EVENT="$(cat || true)"
if [[ -z "${EVENT}" ]]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] pre-tool: empty event" >> "${LOG}"
    exit 0
fi

# Extract the calling agent name (best-effort — schema is evolving)
AGENT="$(echo "${EVENT}" | jq -r '.agent // .subagent // .invoker.name // "unknown"' 2>/dev/null || echo "unknown")"
TOOL="$(echo "${EVENT}" | jq -r '.tool // .tool_name // "unknown"' 2>/dev/null || echo "unknown")"
PROJECT="$(echo "${EVENT}" | jq -r '.context.candidate // .context.project_id // ""' 2>/dev/null || echo "")"

# Don't inject for trivial reads
if [[ "${TOOL}" == "Read" ]] || [[ "${TOOL}" == "Glob" ]] || [[ "${TOOL}" == "Grep" ]]; then
    exit 0
fi

# Skip if AURORA hasn't been initialized yet
if [[ ! -d "${AURORA_HOME}" ]]; then
    exit 0
fi

# Use the recall skill to fetch a scoped slice; capture stdout.
# `-f` (not `-x`): we invoke via `python3 <path>` so the +x bit is irrelevant.
# Using `-x` here was masking the bug where skill scripts shipped without +x —
# the hook would silently exit 0 instead of running the recall pipeline.
RECALL_BIN="${CLAUDE_PROJECT_DIR:-.}/skills/aurora-recall/scripts/recall.py"
if [[ ! -f "${RECALL_BIN}" ]]; then
    # Recall script may not exist yet during early bootstrap — silent skip
    exit 0
fi

CONTEXT_JSON=$(python3 "${RECALL_BIN}" \
    --agent "${AGENT}" \
    --candidate "${PROJECT}" \
    --limit 5 \
    --format minimal 2>/dev/null || echo '{}')

if [[ -z "${CONTEXT_JSON}" ]] || [[ "${CONTEXT_JSON}" == "{}" ]]; then
    exit 0
fi

# Emit a Claude Code context-injection payload
cat <<EOF
{
  "additionalContext": {
    "aurora_memory": ${CONTEXT_JSON},
    "agent": "${AGENT}",
    "scoping_rationale": "Auto-injected by pre-tool-load-memory.sh based on agent role"
  }
}
EOF

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] pre-tool: injected memory for agent=${AGENT} tool=${TOOL}" >> "${LOG}"
exit 0
