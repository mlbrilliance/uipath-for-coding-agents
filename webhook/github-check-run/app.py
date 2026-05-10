"""FastAPI webhook for GitHub check_run.completed → Maestro correlation.

Accepts GitHub's check_run.completed POST, verifies the HMAC, decodes the
result, and posts a correlated message to the right Maestro instance.
"""
from __future__ import annotations

import json
import os
import time
from collections import OrderedDict

import httpx
import structlog
from fastapi import Depends, FastAPI, Request, Response

from maestro_client import post_to_maestro
from security import verify_signature

logger = structlog.get_logger(__name__)

app = FastAPI(title="GitHub Check Run Webhook")

# ── Dedup LRU ─────────────────────────────────────────────────────
# (check_run_id, conclusion, completed_at) → monotonic timestamp
_MAX_LRU = 1024
_DEDUP_TTL = 300  # 5 minutes
_seen: OrderedDict[tuple[int, str, str], float] = OrderedDict()


def _prune_dedup() -> None:
    now = time.monotonic()
    expired = [k for k, v in _seen.items() if now - v > _DEDUP_TTL]
    for k in expired:
        del _seen[k]


def _is_duplicate(check_run_id: int, conclusion: str, completed_at: str) -> bool:
    key = (check_run_id, conclusion, completed_at)
    if key in _seen:
        return True
    _prune_dedup()
    _seen[key] = time.monotonic()
    if len(_seen) > _MAX_LRU:
        _seen.popitem(last=False)
    return False


# ── Maestro client dependency ─────────────────────────────────────


def get_maestro_client() -> httpx.AsyncClient:
    """FastAPI dependency that provides the HTTP client for Maestro calls."""
    return httpx.AsyncClient(timeout=10)


# ── Endpoint ──────────────────────────────────────────────────────


@app.post("/github/check-run")
async def handle_check_run(
    request: Request,
    maestro_client: httpx.AsyncClient = Depends(get_maestro_client),
) -> Response:
    # 1. Read raw body
    body = await request.body()

    # 2. Verify HMAC signature (401 takes precedence)
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(secret, body, signature):
        return Response(status_code=401, content="Invalid signature")

    # 3. Parse JSON
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return Response(status_code=400, content="Malformed JSON")

    # 4. Only handle check_run events with action == "completed"
    event = request.headers.get("X-GitHub-Event", "")
    if event != "check_run":
        return Response(status_code=204)

    action = payload.get("action", "")
    if action != "completed":
        return Response(status_code=204)

    # 5. Extract check_run data
    check_run = payload.get("check_run", {})
    check_run_id = check_run.get("id")
    conclusion = check_run.get("conclusion", "")
    completed_at = check_run.get("completed_at", "")
    html_url = check_run.get("html_url", "")

    # 6. Dedup check — idempotent on duplicate deliveries
    if _is_duplicate(check_run_id, conclusion, completed_at):
        return Response(status_code=200, content="Duplicate event")

    # 7. Correlation key: pr_url if linked, else check_run html_url
    prs = check_run.get("pull_requests", [])
    if prs and prs[0].get("html_url"):
        correlation_key = prs[0]["html_url"]
    else:
        correlation_key = html_url

    # 8. Post correlation message to Maestro
    maestro_payload = {
        "conclusion": conclusion,
        "check_run_id": check_run_id,
        "html_url": html_url,
        "completed_at": completed_at,
    }
    try:
        result = await post_to_maestro(maestro_client, correlation_key, maestro_payload)
    except httpx.HTTPStatusError as exc:
        logger.error("maestro_error", status=exc.response.status_code, url=str(exc.request.url))
        return Response(status_code=502, content="Maestro correlation failed")
    except httpx.RequestError as exc:
        logger.error("maestro_unreachable", url=str(exc.request.url))
        return Response(status_code=502, content="Maestro unreachable")

    if result is None:
        return Response(status_code=204)

    return Response(status_code=200, content="Accepted")
