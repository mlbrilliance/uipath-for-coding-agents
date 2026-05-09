"""UiPath OAuth client-credentials minting and refresh.

This is the canonical implementation. The standalone CLI script at
`skills/aurora-auth/scripts/mint_token.py` is a thin wrapper around
this module so it can be invoked from shell hooks without importing
the full `aurora` package.

Token lifecycle:
    1. mint_token()          — POST to /identity_/connect/token
    2. get_cached_token()    — read sidecar at ~/.uipath/aurora-token.json
    3. ensure_fresh_token()  — refresh if within TOKEN_BUFFER_SECONDS of expiry
    4. write_to_dotenv()     — keep .env in sync so `uip` CLI sees the token
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

REQUIRED_ENV = ("UIPATH_URL", "UIPATH_CLIENT_ID", "UIPATH_CLIENT_SECRET")
TOKEN_BUFFER_SECONDS = 300  # refresh 5 minutes before expiry
DEFAULT_SCOPES = (
    "OR.Folders OR.Execution OR.Jobs OR.Tasks OR.Queues OR.Assets "
    "OR.Robots OR.Machines OR.Monitoring OR.Settings OR.Audit "
    "OR.Administration OR.Users OR.Webhooks OR.License"
)
SIDECAR_PATH = Path.home() / ".uipath" / "aurora-token.json"


@dataclass(frozen=True)
class Token:
    access_token: str
    expires_at: int
    scope: str

    @property
    def needs_refresh(self) -> bool:
        return int(time.time()) > self.expires_at - TOKEN_BUFFER_SECONDS


class AuthError(RuntimeError):
    """Raised on auth-flow failure. Message is safe to log (no secrets)."""


def derive_identity_endpoint(uipath_url: str) -> str:
    """Strip /orchestrator_ suffix, add /identity_/connect/token."""
    base = uipath_url.rstrip("/")
    if base.endswith("/orchestrator_"):
        base = base[: -len("/orchestrator_")]
    elif "/orchestrator_" in base:
        base = base.split("/orchestrator_")[0]
    return f"{base}/identity_/connect/token"


def mint_token(
    *,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    uipath_url: Optional[str] = None,
    scopes: Optional[str] = None,
    write_sidecar: bool = True,
    write_dotenv_path: Optional[Path] = None,
) -> Token:
    """Mint a fresh access token.

    Args default-resolve from os.environ. Raises `AuthError` on any non-200.
    """
    cid = client_id or os.environ.get("UIPATH_CLIENT_ID")
    secret = client_secret or os.environ.get("UIPATH_CLIENT_SECRET")
    url = uipath_url or os.environ.get("UIPATH_URL")
    scope = scopes or os.environ.get("UIPATH_SCOPES") or DEFAULT_SCOPES

    missing = [
        name for name, val in (
            ("UIPATH_CLIENT_ID", cid),
            ("UIPATH_CLIENT_SECRET", secret),
            ("UIPATH_URL", url),
        ) if not val
    ]
    if missing:
        raise AuthError(f"missing env: {', '.join(missing)}")

    endpoint = derive_identity_endpoint(url)  # type: ignore[arg-type]
    body = urlencode({
        "grant_type": "client_credentials",
        "client_id": cid,
        "client_secret": secret,
        "scope": scope,
    })
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        r = httpx.post(endpoint, content=body, headers=headers, timeout=30)
    except httpx.HTTPError as e:
        raise AuthError(f"network error reaching {endpoint}: {e!s}") from e

    if r.status_code != 200:
        # Redact secret from any error payload before raising
        snippet = r.text[:500]
        if secret:
            snippet = snippet.replace(secret, "***REDACTED***")
        raise AuthError(f"HTTP {r.status_code} from {endpoint}: {snippet}")

    payload = r.json()
    token = Token(
        access_token=payload["access_token"],
        expires_at=int(time.time()) + int(payload.get("expires_in", 3600)),
        scope=payload.get("scope", scope or ""),
    )

    if write_sidecar:
        write_sidecar_file(token)

    if write_dotenv_path:
        write_to_dotenv(write_dotenv_path, "UIPATH_ACCESS_TOKEN", token.access_token)

    logger.info("minted UiPath token; expires_at=%s scopes=%s",
                token.expires_at, token.scope)
    return token


def write_sidecar_file(token: Token) -> None:
    """Persist token to ~/.uipath/aurora-token.json for the daemon's cache."""
    SIDECAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    SIDECAR_PATH.write_text(json.dumps({
        "access_token": token.access_token,
        "expires_at": token.expires_at,
        "scope": token.scope,
    }, indent=2))
    SIDECAR_PATH.chmod(0o600)


def get_cached_token() -> Optional[Token]:
    """Read the sidecar file. Returns None if missing or unreadable."""
    if not SIDECAR_PATH.exists():
        return None
    try:
        data = json.loads(SIDECAR_PATH.read_text())
        return Token(
            access_token=data["access_token"],
            expires_at=int(data["expires_at"]),
            scope=data.get("scope", ""),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("malformed token sidecar at %s: %s", SIDECAR_PATH, e)
        return None


def ensure_fresh_token(
    *,
    write_dotenv_path: Optional[Path] = None,
) -> Token:
    """Return a token that's not within TOKEN_BUFFER_SECONDS of expiry.

    Mints if cached is missing or stale. The dotenv-write keeps `uip` CLI happy.
    """
    cached = get_cached_token()
    if cached and not cached.needs_refresh:
        return cached
    return mint_token(write_dotenv_path=write_dotenv_path)


# ---------- .env file helpers ----------

ENV_LINE = re.compile(r"^([A-Z_][A-Z0-9_]*)=")


def write_to_dotenv(path: Path, key: str, value: str) -> None:
    """Replace KEY=… line in .env (or append if missing). Preserves the rest."""
    if not path.exists():
        path.write_text(f"{key}={value}\n", encoding="utf-8")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    new_line = f"{key}={value}"
    found = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith(f"{key}="):
            lines[i] = new_line
            found = True
            break
    if not found:
        lines.append(new_line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
