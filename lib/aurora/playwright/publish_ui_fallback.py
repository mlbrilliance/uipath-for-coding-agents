"""Playwright-driven UI fallback for publishing a Maestro project.

When the reverse-engineered HTTP API is unavailable (e.g. UiPath rotated
the endpoint), this module drives the Studio Web "Publish" button through
a real browser. It is the secondary rail — the HTTP wrapper is primary.

Usage::

    from aurora.playwright.publish_ui_fallback import publish_via_ui
    result = publish_via_ui(
        project_dir=Path("/path/to/maestro-project"),
        version_bump="patch",
    )
    print(result["version"])

This function is sync and intentionally opens a browser. Do NOT call it
from CI — it is for manual / Operate-fleet use only, behind a feature flag
or as a fallback when the HTTP wrapper raises.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PUBLISH_BUTTON_SELECTOR = "button:has-text('Publish')"
STUDIO_WEB_URL_TEMPLATE = "https://cloud.uipath.com/{account}/{tenant}/studio_web/"
PUBLISH_RESPONSE_PATTERN = "/studio_/api/publish"


def publish_via_ui(
    *,
    project_dir: Path,
    version_bump: str = "patch",
    headless: bool = True,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Drive the Studio Web "Publish" button through Playwright.

    Returns a dict with at least ``{"version": str}``.

    This is the UI fallback — prefer ``UiPathClient.publish_maestro_project``
    (the HTTP wrapper) for headless / CI use.
    """
    from playwright.sync_api import sync_playwright

    account = os.environ.get("UIPATH_ACCOUNT_SLUG", "")
    tenant = os.environ.get("UIPATH_TENANT_SLUG", "")
    if not account or not tenant:
        raise RuntimeError(
            "UIPATH_ACCOUNT_SLUG and UIPATH_TENANT_SLUG must be set "
            "for the UI fallback publish path."
        )

    studio_url = STUDIO_WEB_URL_TEMPLATE.format(account=account, tenant=tenant)
    result: dict[str, Any] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        captured_response: dict[str, Any] = {}

        def _on_response(response: Any) -> None:
            """Intercept the publish response to extract the version."""
            if PUBLISH_RESPONSE_PATTERN in response.url and response.request.method == "POST":
                try:
                    body = response.json()
                    captured_response.update(body)
                except Exception:
                    logger.warning("could not parse publish response JSON from %s", response.url)

        page.on("response", _on_response)

        logger.info("opening Studio Web for UI publish: %s", studio_url)
        page.goto(studio_url)

        # Wait for the page to load and project list to appear
        page.wait_for_load_state("networkidle")

        # Click the Publish button
        logger.info("clicking Publish button for project_dir=%s", project_dir)
        publish_btn = page.wait_for_selector(PUBLISH_BUTTON_SELECTOR, timeout=timeout_seconds * 1000)
        if publish_btn:
            publish_btn.click()
        else:
            raise RuntimeError("Publish button not found in Studio Web UI")

        # Wait for the publish response
        import time
        deadline = time.time() + timeout_seconds
        while not captured_response and time.time() < deadline:
            page.wait_for_timeout(1000)

        browser.close()

    if not captured_response:
        raise RuntimeError("no publish response captured within timeout")

    version = captured_response.get("version", "unknown")
    logger.info("UI fallback publish complete: version=%s", version)

    return {"version": version, "status": captured_response.get("status", "Published")}
