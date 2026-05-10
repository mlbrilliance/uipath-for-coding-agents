#!/usr/bin/env bash
# AURORA hook: PostToolUse
# Capture fingerprints + learnings after every tool call.
#
# Detects two outcomes:
#   1. Tool failed -> append a fault event to events.jsonl, classify, write learning
#   2. Tool succeeded -> if the agent emitted a structured "learning:" line, capture it
#
# Never blocks; always exits 0.

set -euo pipefail

AURORA_HOME="${AURORA_HOME:-${HOME}/.aurora}"
LOG="${AURORA_HOME}/hooks.log"
EVENTS="${AURORA_HOME}/events.jsonl"
LEARNINGS_DIR="${AURORA_HOME}/learnings"
DATE="$(date -u +%Y-%m-%d)"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "${LEARNINGS_DIR}" "${AURORA_HOME}"

EVENT="$(cat || true)"
if [[ -z "${EVENT}" ]]; then
    exit 0
fi

# Parse the event
AGENT="$(echo "${EVENT}" | jq -r '.agent // .subagent // .invoker.name // "unknown"' 2>/dev/null || echo "unknown")"
TOOL="$(echo "${EVENT}" | jq -r '.tool // .tool_name // "unknown"' 2>/dev/null || echo "unknown")"
SUCCESS="$(echo "${EVENT}" | jq -r '.result.success // .success // true' 2>/dev/null || echo "true")"
ERROR_MSG="$(echo "${EVENT}" | jq -r '.result.error // .error // ""' 2>/dev/null || echo "")"
PROJECT="$(echo "${EVENT}" | jq -r '.context.candidate // .context.project_id // ""' 2>/dev/null || echo "")"

# 1. On failure, fingerprint
if [[ "${SUCCESS}" != "true" ]] && [[ -n "${ERROR_MSG}" ]]; then
    EVENT_PAYLOAD=$(jq -nc \
        --arg ts "${TS}" \
        --arg agent "${AGENT}" \
        --arg tool "${TOOL}" \
        --arg err "${ERROR_MSG}" \
        --arg proj "${PROJECT}" \
        '{
            ts: $ts,
            kind: "tool_failed",
            scope: { agent: $agent, tool: $tool, project: $proj },
            details: { message: $err }
        }')
    echo "${EVENT_PAYLOAD}" >> "${EVENTS}"

    # `-f` (not `-x`): we invoke via `python3 <path>` so +x is irrelevant.
    # Using `-x` here was masking the bug where the script shipped without +x.
    FP_BIN="${CLAUDE_PROJECT_DIR:-.}/skills/aurora-fingerprint/scripts/cluster.py"
    if [[ -f "${FP_BIN}" ]]; then
        TMP="$(mktemp)"
        echo "${EVENT_PAYLOAD}" > "${TMP}"
        python3 "${FP_BIN}" classify --event-file "${TMP}" >> "${LOG}" 2>&1 || true
        rm -f "${TMP}"
    fi
fi

# 2. On any tool call, look for an explicit learning line in the agent output
LEARNING="$(echo "${EVENT}" | jq -r '.result.output // .output // ""' 2>/dev/null | grep -E '^learning:' | head -1 || echo "")"
if [[ -n "${LEARNING}" ]]; then
    SUMMARY="${LEARNING#learning:}"
    SUMMARY="${SUMMARY# }"
    LEARNING_PAYLOAD=$(jq -nc \
        --arg ts "${TS}" \
        --arg agent "${AGENT}" \
        --arg proj "${PROJECT}" \
        --arg summary "${SUMMARY}" \
        '{
            ts: $ts,
            agent: $agent,
            project_id: $proj,
            kind: "agent-learning",
            summary: $summary
        }')
    echo "${LEARNING_PAYLOAD}" >> "${LEARNINGS_DIR}/${DATE}.jsonl"
fi

echo "[${TS}] post-tool: agent=${AGENT} tool=${TOOL} success=${SUCCESS}" >> "${LOG}"
exit 0
