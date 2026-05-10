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

    # 1. Resolve instance_id from pr_url
    r = await client.get(
        f"{base}/maestro_/api/instances",
        params={"correlation.pr_url": pr_url, "$top": 1},
        headers=headers,
    )
    r.raise_for_status()
    instances = r.json().get("value", [])
    if not instances:
        logger.warning("no_maestro_instance_for_pr", pr_url=pr_url)
        return None
    instance_id = instances[0]["id"]

    # 2. Post the correlation message
    r = await client.post(
        f"{base}/maestro_/api/instances/{instance_id}/message",
        params={"key": pr_url},
        headers=headers,
        json=payload,
    )
    r.raise_for_status()
    return instance_id
