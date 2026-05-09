---
name: aurora-auth
description: Mint and refresh UiPath Automation Cloud OAuth tokens via the External Application client-credentials grant. Reads UIPATH_CLIENT_ID and UIPATH_CLIENT_SECRET from .env, requests the scope list from policy.yaml::uipath_scopes, writes the live access token to UIPATH_ACCESS_TOKEN so the uip CLI can use it without re-auth, and refreshes proactively before the 1-hour expiry. Use this skill at the start of every Conductor run, before any uip CLI or uipath-python SDK call, and whenever Sentry emits a `kind: auth_failed` event.
---

# aurora-auth

UiPath Automation Cloud uses OAuth 2.0 with the client-credentials grant for confidential External Applications. AURORA mints tokens at runtime — never relies on a stale `UIPATH_ACCESS_TOKEN` in `.env` — and writes them back so the `uip` CLI and `uipath-python` SDK both see fresh credentials.

## When to invoke

- On `aurora start` boot
- Before any call that touches Orchestrator (Sentry, Surgeon, Concierge, Auditor)
- When Sentry emits `kind: auth_failed`
- When the cached token's `expires_at` is within 5 minutes

## How to use

```bash
python scripts/mint_token.py [--scopes "OR.Folders OR.Tasks ..."]
```

If `--scopes` is omitted, reads `policy.yaml::uipath_scopes` and joins with spaces.

The script:
1. Reads `UIPATH_URL`, `UIPATH_CLIENT_ID`, `UIPATH_CLIENT_SECRET` from `.env` (or environment)
2. Computes the identity-server endpoint: strips `/orchestrator_` from `UIPATH_URL`, appends `/identity_/connect/token`
3. POSTs `grant_type=client_credentials&client_id=…&client_secret=…&scope=…` (form-encoded)
4. On 200, writes the token to `.env` as `UIPATH_ACCESS_TOKEN=…` (replaces any existing line)
5. Writes a sidecar at `~/.uipath/aurora-token.json` with `{access_token, expires_at, scope}` for the daemon's in-process cache
6. On non-200, raises with a clear message — `invalid_client`, `invalid_scope`, network — and the corresponding remediation hint

## Token refresh strategy

Tokens have `expires_in: 3600`. AURORA refreshes when `now > expires_at - 300s` (5-minute buffer). The Conductor's daemon mode (`lib/aurora/conductor.py`) holds the cache and refreshes opportunistically; agents in Claude Code subagent mode invoke the script directly when needed.

## Anti-patterns

- Don't paste a curl-test token into `UIPATH_ACCESS_TOKEN` in `.env`. Curl-test tokens use a subset of scopes; AURORA requests the full list.
- Don't catch and swallow auth errors. Surface them; let Sentry → Diagnostician → Surgeon handle.
- Don't store the secret anywhere other than `.env`. Never log it. The script must redact `client_secret` from any error trace.
- Don't request `offline_access` for a confidential External App. That's user-scope only.

## Required external state

- `.env` populated with `UIPATH_URL`, `UIPATH_CLIENT_ID`, `UIPATH_CLIENT_SECRET`
- The External App in Automation Cloud has the scope set granted (verify with the curl in `CLAUDE.md`)
