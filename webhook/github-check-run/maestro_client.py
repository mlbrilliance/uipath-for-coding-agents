"""Maestro correlation client — resolve instance and post message."""
from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


async def post_to_maestro(
    client: httpx.AsyncClient,
    pr_url: str,
    payload: dict[str, Any],
) -> str | None:
    """Resolve the Maestro instance for *pr_url*, then post a correlation message.

    Returns the ``instance_id`` on success, or ``None`` when no matching
    instance is found.
    """
    base = os.environ.get("UIPATH_URL", "").rstrip("/")
    folder = os.environ.get("UIPATH_FOLDER", "")
    token = os.environ.get("UIPATH_ACCESS_TOKEN", "")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-UIPATH-OrganizationUnitId": folder,
        "Content-Type": "application/json",
    }

    # 1. Resolve instance_id from pr_url.
    # The Maestro instance-list endpoint may return non-JSON (HTML error page,
    # empty body) when the Maestro process isn't deployed in the folder, or
    # when the endpoint doesn't exist on this tenant version. Treat those
    # cases as "no correlatable instance" and let the caller return 204.
    r = await client.get(
        f"{base}/maestro_/api/instances",
        params={"correlation.pr_url": pr_url, "$top": 1},
        headers=headers,
    )
    if r.status_code >= 400:
        logger.warning(
            "maestro_lookup_http_error", pr_url=pr_url, status=r.status_code
        )
        return None
    try:
        instances = r.json().get("value", [])
    except (ValueError, AttributeError):
        # Non-JSON response or unexpected shape — treat as no-match.
        logger.warning(
            "maestro_lookup_non_json", pr_url=pr_url, body_preview=r.text[:200]
        )
        return None
    if not instances:
        logger.warning("no_maestro_instance_for_pr", pr_url=pr_url)
        return None
    instance_id = instances[0].get("id")
    if not instance_id:
        logger.warning("maestro_instance_missing_id", pr_url=pr_url, instance=instances[0])
        return None

    # 2. Post the correlation message
    r = await client.post(
        f"{base}/maestro_/api/instances/{instance_id}/message",
        params={"key": pr_url},
        headers=headers,
        json=payload,
    )
    r.raise_for_status()
    return instance_id
