"""Studio Web traffic-capture tool.

One-shot, manual: opens Studio Web in a real browser, the human logs in and
clicks Publish; this script intercepts the network call and writes the
request shape to ``tests/fixtures/maestro/publish_request.json``.

Usage::

    python -m aurora.playwright.capture

Do NOT automate the login. The human must authenticate interactively.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CAPTURE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "tests" / "fixtures" / "maestro"
PUBLISH_URL_PATTERN = "/studio_/api/publish"


def capture_publish_request(
    *,
    account_slug: str | None = None,
    tenant_slug: str | None = None,
    output_path: Path | None = None,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Open Studio Web, wait for the human to publish, capture the HTTP request.

    Returns the captured request dict (also written to ``output_path``).

    This function is intended to be called **manually** — it opens a real
    browser and waits for the user to click Publish in Studio Web.
    """
    from playwright.sync_api import sync_playwright

    account = account_slug or os.environ.get("UIPATH_ACCOUNT_SLUG", "")
    tenant = tenant_slug or os.environ.get("UIPATH_TENANT_SLUG", "")
    if not account or not tenant:
        raise RuntimeError(
            "UIPATH_ACCOUNT_SLUG and UIPATH_TENANT_SLUG must be set "
            "(or passed as arguments) to build the Studio Web URL."
        )

    studio_url = f"https://cloud.uipath.com/{account}/{tenant}/studio_web/"
    out = output_path or CAPTURE_DIR / "publish_request.json"
    captured: dict[str, Any] = {}

    def _on_request_finished(request: Any) -> None:
        """Intercept requests matching the publish URL pattern."""
        url = request.url
        if PUBLISH_URL_PATTERN in url and request.method == "POST":
            nonlocal captured
            try:
                body = request.post_data
                parsed_body = json.loads(body) if body else {}
            except (json.JSONDecodeError, TypeError):
                parsed_body = {}

            captured = {
                "synthetic": False,
                "note": "Captured via lib/aurora/playwright/capture.py from a live Studio Web session.",
                "method": request.method,
                "url_path": _extract_url_path(url),
                "headers": dict(request.headers),
                "body": parsed_body,
            }
            logger.info("captured publish request: %s %s", request.method, url)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # Listen for network requests
        page.on("requestfinished", _on_request_finished)

        logger.info("Opening Studio Web: %s", studio_url)
        logger.info("Please log in, select your Maestro project, and click Publish.")
        logger.info("Waiting up to %d seconds for the publish request…", timeout_seconds)

        page.goto(studio_url)

        # Wait until we capture the publish request or timeout
        import time
        deadline = time.time() + timeout_seconds
        while not captured and time.time() < deadline:
            page.wait_for_timeout(1000)

        browser.close()

    if not captured:
        logger.error("No publish request captured within timeout.")
        return {}

    # Sanitise headers — remove the live bearer token
    sanitised_headers = {}
    for key, value in captured.get("headers", {}).items():
        if key.lower() == "authorization":
            sanitised_headers[key] = "Bearer {{UIPATH_ACCESS_TOKEN}}"
        elif key.lower() == "x-uipath-organizationunitid":
            sanitised_headers[key] = "{{folder_id}}"
        else:
            sanitised_headers[key] = value
    captured["headers"] = sanitised_headers

    # Write to fixture file
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(captured, indent=2) + "\n")
    logger.info("wrote captured fixture to %s", out)

    return captured


def _extract_url_path(full_url: str) -> str:
    """Strip scheme + host, return just the path component."""
    from urllib.parse import urlparse
    parsed = urlparse(full_url)
    return parsed.path


def main() -> None:
    """CLI entry point for manual capture."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = capture_publish_request()
    if result:
        print(f"✓ Captured publish request → {CAPTURE_DIR / 'publish_request.json'}")
    else:
        print("✗ No publish request captured.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
