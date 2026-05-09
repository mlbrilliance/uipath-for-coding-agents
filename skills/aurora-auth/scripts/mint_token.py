#!/usr/bin/env python3
"""Mint a UiPath Automation Cloud OAuth token via client-credentials grant.

Reads .env (current dir or repo root), POSTs to the identity-server token
endpoint, writes the live access token back to .env and a sidecar at
~/.uipath/aurora-token.json.

Exit codes:
  0  — success
  1  — missing required env var
  2  — non-200 from identity server (auth/scope/network)
  3  — malformed UIPATH_URL
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx


REQUIRED_ENV = ("UIPATH_URL", "UIPATH_CLIENT_ID", "UIPATH_CLIENT_SECRET")
DEFAULT_SCOPES = (
    "OR.Folders OR.Execution OR.Jobs OR.Tasks OR.Queues OR.Assets "
    "OR.Robots OR.Machines OR.Monitoring OR.Settings OR.Audit "
    "OR.Administration OR.Users OR.Webhooks OR.License"
)
TOKEN_BUFFER_SECONDS = 300


def find_dotenv() -> Optional[Path]:
    """Walk up from cwd looking for a .env file, max 5 levels."""
    cwd = Path.cwd().resolve()
    for d in [cwd, *cwd.parents][:6]:
        candidate = d / ".env"
        if candidate.exists():
            return candidate
    return None


def load_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env parser — KEY=VALUE per line, no shell expansion."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        if v.startswith(("'", '"')) and v.endswith(("'", '"')):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def write_env_var(path: Path, key: str, value: str) -> None:
    """Replace KEY=… line in .env (or append if missing). Preserves the rest."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    new_line = f"{key}={value}"
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            lines[i] = new_line
            found = True
            break
    if not found:
        lines.append(new_line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def derive_identity_endpoint(uipath_url: str) -> str:
    """Strip /orchestrator_ suffix, add /identity_/connect/token."""
    base = uipath_url.rstrip("/")
    if base.endswith("/orchestrator_"):
        base = base[: -len("/orchestrator_")]
    elif "/orchestrator_" in base:
        base = base.split("/orchestrator_")[0]
    return f"{base}/identity_/connect/token"


def mint(client_id: str, client_secret: str, endpoint: str, scopes: str) -> dict:
    """POST to /identity_/connect/token. Raises on non-200."""
    body = urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scopes,
    })
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = httpx.post(endpoint, content=body, headers=headers, timeout=30)
    if r.status_code != 200:
        # Redact secrets from any error
        raise SystemExit(
            f"[aurora-auth] HTTP {r.status_code} from {endpoint}: "
            f"{r.text[:500].replace(client_secret, '***REDACTED***')}"
        )
    return r.json()


def main() -> int:
    p = argparse.ArgumentParser(description="Mint a UiPath OAuth client-credentials token")
    p.add_argument("--scopes", default=None, help="space-separated scope list")
    p.add_argument("--quiet", action="store_true", help="no stdout on success")
    args = p.parse_args()

    dotenv_path = find_dotenv()
    if dotenv_path:
        env = load_dotenv(dotenv_path)
        for k, v in env.items():
            os.environ.setdefault(k, v)
    else:
        if not args.quiet:
            print("[aurora-auth] no .env found; using process env only", file=sys.stderr)

    missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
    if missing:
        print(f"[aurora-auth] missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    uipath_url = os.environ["UIPATH_URL"]
    if "/orchestrator_" not in uipath_url and not uipath_url.startswith("http"):
        print(f"[aurora-auth] malformed UIPATH_URL: {uipath_url!r}", file=sys.stderr)
        return 3

    scopes = args.scopes or os.environ.get("UIPATH_SCOPES") or DEFAULT_SCOPES
    endpoint = derive_identity_endpoint(uipath_url)

    token = mint(
        os.environ["UIPATH_CLIENT_ID"],
        os.environ["UIPATH_CLIENT_SECRET"],
        endpoint,
        scopes,
    )
    access = token["access_token"]
    expires_at = int(time.time()) + int(token.get("expires_in", 3600))

    # Write to .env so uip CLI sees it
    if dotenv_path:
        write_env_var(dotenv_path, "UIPATH_ACCESS_TOKEN", access)

    # Write sidecar for the daemon's in-process cache
    sidecar = Path.home() / ".uipath" / "aurora-token.json"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps({
        "access_token": access,
        "expires_at": expires_at,
        "scope": token.get("scope", scopes),
    }, indent=2))

    if not args.quiet:
        scope_returned = token.get("scope", "")
        print(f"[aurora-auth] minted token; expires_at={expires_at}; scopes={scope_returned}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
