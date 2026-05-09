#!/usr/bin/env bash
# AURORA demo: undo break.sh's failure injection.
# Restores .env from .env.break-backup if it exists.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV="${ROOT}/.env"
BACKUP="${ROOT}/.env.break-backup"

if [[ ! -f "${BACKUP}" ]]; then
    echo "[restore] no backup at ${BACKUP}; nothing to restore" >&2
    exit 1
fi

mv "${BACKUP}" "${ENV}"
echo "[restore] .env restored from backup; backup removed"
echo "[restore] you may want to: aurora policy reload"
