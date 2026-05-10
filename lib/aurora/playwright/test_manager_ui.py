"""Playwright-driven UI fallback for Test Manager automation linkage.

When the documented HTTP API for ``link_automation`` is unreachable
(e.g. the endpoint rotates, or Test Manager is down), this module drives
the Test Manager web UI through a real browser to perform the same
"Select Automation" linkage step that the API call automates.

Usage::

    from aurora.playwright.test_manager_ui import link_via_ui
    result = link_via_ui(
        test_case_id="TC-1",
        package_id="MyPackage",
        entry_point="Main.xaml",
    )
    print(result.link_id)

This function is sync and intentionally opens a browser. Do NOT call
it from CI — the API rail in ``aurora.test_manager.TestManagerClient``
is primary; this is the fallback for when the API rotates and the
Operate fleet needs to keep linking while T-E1's docs runbook is used
to re-capture the new shape.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from aurora.test_manager import LinkResult, _parse_link_response

logger = logging.getLogger(__name__)

LINK_BUTTON_SELECTOR = "button:has-text('Select Automation')"
TEST_MANAGER_URL_TEMPLATE = (
    "https://cloud.uipath.com/{account}/{tenant}/test_/test-cases/{test_case_id}"
)
LINK_RESPONSE_PATTERN = "/test_/api/v1/"


def link_via_ui(
    *,
    test_case_id: str,
    package_id: str,
    entry_point: str,
    headless: bool = True,
    timeout_seconds: int = 300,
) -> LinkResult:
    """Drive the Test Manager UI to perform automation linkage.

    Returns a :class:`aurora.test_manager.LinkResult` whose ``link_id`` is
    extracted from the network response captured during the click.

    This is the UI fallback — prefer
    :meth:`aurora.test_manager.TestManagerClient.link_automation` (HTTP)
    for headless / CI use. Skipped automatically by tests when the
    ``playwright`` optional dep isn't installed.
    """
    from playwright.sync_api import sync_playwright

    account = os.environ.get("UIPATH_ACCOUNT_SLUG", "")
    tenant = os.environ.get("UIPATH_TENANT_SLUG", "")
    if not account or not tenant:
        raise RuntimeError(
            "UIPATH_ACCOUNT_SLUG and UIPATH_TENANT_SLUG must be set "
            "for the UI fallback link path."
        )

    test_manager_url = TEST_MANAGER_URL_TEMPLATE.format(
        account=account,
        tenant=tenant,
        test_case_id=test_case_id,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        captured_response: dict[str, Any] = {}

        def _on_response(response: Any) -> None:
            """Intercept the link response to extract the link id."""
            if (
                LINK_RESPONSE_PATTERN in response.url
                and "link" in response.url.lower()
                and response.request.method == "POST"
            ):
                try:
                    body = response.json()
                    captured_response.update(body)
                except Exception:
                    logger.warning(
                        "could not parse link response JSON from %s", response.url
                    )

        page.on("response", _on_response)

        logger.info(
            "opening Test Manager for UI linkage: %s (package=%s entry=%s)",
            test_manager_url,
            package_id,
            entry_point,
        )
        page.goto(test_manager_url)
        page.wait_for_load_state("networkidle")

        logger.info("clicking 'Select Automation' for test_case_id=%s", test_case_id)
        link_btn = page.wait_for_selector(
            LINK_BUTTON_SELECTOR, timeout=timeout_seconds * 1000
        )
        if link_btn is None:
            raise RuntimeError("'Select Automation' button not found in Test Manager UI")
        link_btn.click()

        deadline = time.time() + timeout_seconds
        while not captured_response and time.time() < deadline:
            page.wait_for_timeout(1000)

        browser.close()

    if not captured_response:
        raise RuntimeError("no link response captured within timeout")

    result = _parse_link_response(captured_response)
    logger.info(
        "UI fallback link complete: link_id=%s linked=%s",
        result.link_id,
        result.linked,
    )
    return result
