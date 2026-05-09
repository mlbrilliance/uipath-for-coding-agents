#!/usr/bin/env bash
# AURORA bootstrap script — one-shot install on a fresh Ubuntu VPS.
#
# What it does:
#   1. Verifies prerequisites (node, python, claude, git)
#   2. Installs the @uipath/cli npm package
#   3. Installs the seven official UiPath skills (interactive)
#   4. Initializes .env from .env.example if missing
#   5. Runs `claude login` if Claude OAuth credentials are missing
#   6. Installs Python deps with uv
#   7. Adds AURORA as a Claude Code plugin
#   8. Validates policy.yaml
#   9. Runs the unit-test suite to confirm everything imports
#  10. Prints next-step instructions

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

# ANSI colors for readability
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

step() { echo -e "${GREEN}==>${NC} $1"; }
warn() { echo -e "${YELLOW}!! ${NC} $1" >&2; }
fail() { echo -e "${RED}xx ${NC} $1" >&2; exit 1; }

# ---------- 1. Prerequisites ----------

step "1/10  Checking prerequisites"
command -v node    >/dev/null 2>&1 || fail "node not found. Install Node.js 18+ first."
command -v npm     >/dev/null 2>&1 || fail "npm not found."
command -v python3 >/dev/null 2>&1 || fail "python3 not found. Install Python 3.11+ first."
command -v git     >/dev/null 2>&1 || fail "git not found."
command -v claude  >/dev/null 2>&1 || warn "claude CLI not found — install Claude Code before \`aurora start\`."

if ! command -v uv >/dev/null 2>&1; then
    step "Installing uv (Python package manager)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # shellcheck disable=SC1091
    [ -f "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"
fi

# ---------- 2. UiPath CLI ----------

step "2/10  Installing @uipath/cli"
if ! command -v uipath >/dev/null 2>&1; then
    npm install -g @uipath/cli
else
    echo "    @uipath/cli already installed: $(uipath --version 2>/dev/null || echo unknown)"
fi

# ---------- 3. Official UiPath skills ----------

step "3/10  Installing official UiPath skills"
echo "    Run \`uipath skills install\` from this directory and select all seven skills."
read -r -p "    Run uipath skills install now? [Y/n] " yn
case "${yn:-y}" in
    [Yy]*)  uipath skills install || warn "uipath skills install non-zero; continuing" ;;
    *)      echo "    Skipping. Re-run \`uipath skills install\` later." ;;
esac

# ---------- 4. .env initialization ----------

step "4/10  Initializing .env"
if [[ ! -f "${ROOT}/.env" ]]; then
    cp "${ROOT}/.env.example" "${ROOT}/.env"
    warn "Created .env from .env.example. EDIT IT before \`aurora start\`."
    warn "  Required: UIPATH_URL, UIPATH_CLIENT_ID, UIPATH_CLIENT_SECRET, GITHUB_TOKEN"
else
    echo "    .env exists; not touching"
fi

# ---------- 5. Claude OAuth ----------

step "5/10  Checking Claude subscription OAuth"
CLAUDE_CRED="${HOME}/.claude/credentials.json"
if [[ ! -f "${CLAUDE_CRED}" ]]; then
    warn "No Claude credentials at ${CLAUDE_CRED}"
    if command -v claude >/dev/null 2>&1; then
        read -r -p "    Run \`claude login\` now? [Y/n] " yn
        case "${yn:-y}" in
            [Yy]*) claude login ;;
            *)     warn "Skipping. AURORA daemons will fail until you do this." ;;
        esac
    else
        warn "claude CLI not on PATH; install Claude Code and run \`claude login\` later."
    fi
else
    echo "    Claude credentials found"
fi

# ---------- 6. Python deps ----------

step "6/10  Installing Python dependencies (uv sync --extra dev)"
uv sync --extra dev

# ---------- 7. AURORA plugin ----------

step "7/10  Installing AURORA as a Claude Code plugin"
if command -v claude >/dev/null 2>&1; then
    if ! claude plugin marketplace list 2>/dev/null | grep -qi 'aurora'; then
        claude plugin marketplace add "${ROOT}" || warn "marketplace add failed; continuing"
    fi
    if ! claude plugin list 2>/dev/null | grep -qi '^aurora'; then
        claude plugin install aurora@aurora-marketplace || warn "plugin install failed; do it manually later"
    fi
else
    warn "Skipping plugin install (claude CLI missing)"
fi

# ---------- 8. Symlink AGENTS.md ----------

step "8/10  Linking AGENTS.md -> CLAUDE.md (Codex/Cursor compat)"
if [[ ! -e "${ROOT}/AGENTS.md" ]]; then
    ln -s CLAUDE.md "${ROOT}/AGENTS.md"
    echo "    symlink created"
elif [[ -L "${ROOT}/AGENTS.md" ]]; then
    echo "    symlink already exists"
else
    warn "AGENTS.md exists but isn't a symlink. Inspect manually."
fi

# ---------- 9. Policy validation ----------

step "9/10  Validating policy.yaml"
# Export .env values so policy's ${VAR} references resolve. Uses python so values
# containing shell metacharacters (parens, $, etc) survive without manual quoting.
if [[ -f "${ROOT}/.env" ]]; then
    while IFS= read -r line; do
        [[ -n "${line}" ]] && export "${line?}"
    done < <(python3 -c "
import os
for raw in open('${ROOT}/.env', encoding='utf-8'):
    s = raw.strip()
    if not s or s.startswith('#') or '=' not in s:
        continue
    k, _, v = s.partition('=')
    k = k.strip()
    v = v.strip().strip('\"').strip(\"'\")
    if k.isidentifier():
        print(f'{k}={v}')
")
fi
if uv run aurora policy validate; then
    echo "    policy: valid"
else
    warn "policy.yaml is invalid. Fix the errors above before \`aurora start\`."
fi

# ---------- 10. Unit tests ----------

step "10/10 Running unit-test sanity suite"
if uv run pytest tests/unit -q --no-header; then
    echo "    unit tests: green"
else
    warn "Unit tests failed. AURORA will probably still work but the regression suite is broken."
fi

# ---------- Done ----------

cat <<EOF

$(echo -e "${GREEN}=============================================================
  AURORA bootstrap complete.
=============================================================${NC}")

Next steps:
  1.  Edit .env (especially UIPATH_*, GITHUB_*, AURORA_EMERGENCY_APPROVERS)
  2.  Verify the OAuth round-trip:
        curl -X POST "\${UIPATH_URL%/orchestrator_}/identity_/connect/token" \\
          -H "Content-Type: application/x-www-form-urlencoded" \\
          --data-urlencode "grant_type=client_credentials" \\
          --data-urlencode "client_id=\${UIPATH_CLIENT_ID}" \\
          --data-urlencode "client_secret=\${UIPATH_CLIENT_SECRET}" \\
          --data-urlencode "scope=OR.Folders OR.Tasks"
  3.  Boot the swarm:
        aurora start
  4.  Open the dashboard in another shell:
        aurora status
  5.  Walk through the demo:
        See docs/demo-script.md

Files of interest:
  CLAUDE.md             — project context Claude Code reads on every session
  policy.yaml           — operating policy (the contract)
  agents/               — 19 subagent definitions
  skills/               — 10 AURORA skills + 7 official UiPath skills
  examples/oss-supply-chain-defender/  — the demo target

If something breaks, run /aurora-feedback from inside Claude Code.

EOF
