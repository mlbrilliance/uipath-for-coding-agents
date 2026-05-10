#!/usr/bin/env bash
# Install AURORA as a systemd service so the Operate-fleet daemons survive
# Claude Code session boundaries. Run as root or with sudo.
#
# Creates two units:
#   - aurora.service       (Conductor + Sentry + cron)
#   - aurora-mcp.service   (the MCP server, only useful if you serve MCP over TCP)
#
# Default user is `aurora`; create with: sudo useradd -r -s /bin/false aurora

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run as root or with sudo." >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${AURORA_SERVICE_USER:-aurora}"
ENV_FILE="${ROOT}/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "No .env at ${ENV_FILE}. Copy from .env.example and fill in first." >&2
    exit 1
fi

# Ensure user exists
if ! id "${SERVICE_USER}" &>/dev/null; then
    echo "==> creating system user ${SERVICE_USER}"
    useradd -r -s /bin/false "${SERVICE_USER}"
fi

# Ensure runtime dirs are writable
mkdir -p /opt/aurora /opt/aurora/memory /opt/aurora/worktrees /opt/aurora/learnings
chown -R "${SERVICE_USER}:${SERVICE_USER}" /opt/aurora

cat > /etc/systemd/system/aurora.service <<EOF
[Unit]
Description=AURORA — UiPath coding-agent swarm
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${ROOT}
EnvironmentFile=${ENV_FILE}
ExecStart=/usr/bin/env uv run python -m aurora.conductor
Restart=on-failure
RestartSec=15
TimeoutStopSec=30

# Resource limits
LimitNOFILE=4096
MemoryHigh=2G
MemoryMax=4G

# Hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/opt/aurora ${ROOT}/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable aurora.service

cat <<EOF

systemd unit installed.

To start AURORA in the background:
    sudo systemctl start aurora

To watch its logs:
    sudo journalctl -u aurora -f

To stop:
    sudo systemctl stop aurora

To see status:
    sudo systemctl status aurora

NOTE: this user (${SERVICE_USER}) needs read access to ~/.claude/credentials.json.
The simplest setup is to run \`claude login\` once as the service user:
    sudo -u ${SERVICE_USER} claude login

EOF
