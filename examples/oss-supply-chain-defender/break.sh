#!/usr/bin/env bash
# AURORA demo: failure injection.
#
# Replaces GITHUB_TOKEN in .env with a deliberately invalid value, then
# triggers a Maestro instance. The expected sequence is:
#
#   1. ResolveLockfiles step calls GitHub API with invalid token
#   2. UiPath job fails with HTTP 401
#   3. Sentry catches `kind: job_failed` within ~30s
#   4. Diagnostician fingerprints `auth-failed/token-expired`
#      Cluster matches a prior fingerprint (if you've run break.sh before),
#      confidence > 0.7
#   5. Surgeon spawns; rotates to GITHUB_TOKEN_FALLBACK via aurora-auth +
#      Orchestrator Asset rotation
#   6. Job retries automatically and goes green
#   7. Compost step (later that night) opens a PR proposing a skill update
#      to the auth-rotation refinement
#
# Use ./restore.sh to put the original token back manually if Surgeon doesn't
# get there or you want to abort.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV="${ROOT}/.env"
BACKUP="${ROOT}/.env.break-backup"

if [[ ! -f "${ENV}" ]]; then
    echo "[break] no .env found at ${ENV}; aborting" >&2
    exit 1
fi

if [[ -f "${BACKUP}" ]]; then
    echo "[break] backup already exists at ${BACKUP}; restore first or remove it" >&2
    exit 1
fi

cp "${ENV}" "${BACKUP}"
echo "[break] backed up .env -> ${BACKUP}"

# Replace GITHUB_TOKEN with an invalid value (real-looking format so
# hashcheckers don't bail on shape).
INVALID="ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
if grep -q '^GITHUB_TOKEN=' "${ENV}"; then
    sed -i.bak "s|^GITHUB_TOKEN=.*$|GITHUB_TOKEN=${INVALID}|" "${ENV}"
    rm -f "${ENV}.bak"
else
    printf '\nGITHUB_TOKEN=%s\n' "${INVALID}" >> "${ENV}"
fi

echo "[break] GITHUB_TOKEN set to invalid value"
echo "[break] now triggering a manual Maestro instance via uip CLI..."

# Try to start an instance via the uip CLI; fall back to a SDK invocation if
# uip isn't on PATH or the process isn't deployed yet.
if command -v uip >/dev/null 2>&1; then
    if uip maestro start --process OssSupplyChainDefender --folder AURORA-Demo >/dev/null 2>&1; then
        echo "[break] Maestro instance started"
    else
        echo "[break] uip maestro start failed; trying python fallback"
        uv run python -m aurora.cli recall "tickle the demo" --limit 0 || true
        cat <<'EOF'
[break] No Maestro instance started — you can either:
  1. Open Orchestrator UI -> AURORA-Demo -> OssSupplyChainDefender -> Start
  2. Run: uv run python -c "from aurora.uipath_client import UiPathClient; UiPathClient().sdk.processes.invoke(name='OssSupplyChainDefender')"
EOF
    fi
fi

cat <<EOF

[break] DONE. Now watch:

  - aurora status                    (TUI dashboard; agent activity)
  - tail -f /opt/aurora/events.jsonl (Sentry stream)
  - tail -f /opt/aurora/hooks.log    (hook activity)

Expected: within 1-2 minutes, Sentry emits job_failed, Diagnostician
fingerprints auth-failed/token-expired, Surgeon dispatches, opens a PR
that rotates to GITHUB_TOKEN_FALLBACK, and the next attempt goes green.

If Surgeon doesn't recover within 5 minutes, run ./restore.sh to put the
real token back manually.
EOF
