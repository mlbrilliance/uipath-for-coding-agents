"""Windows-side capture of UiPath Studio Web's Maestro publish HTTP request.

WHY THIS EXISTS
---------------
Studio Web's Publish button hits an undocumented internal HTTP API that
needs a real Auth0/OIDC user session. We can't drive it from a headless
Linux VPS (no display, no session cookies). This script runs on your
Windows machine with a real Chromium window so you can log in normally,
click Publish on a Maestro project, and the script intercepts the
resulting POST and writes its shape to disk. The captured fixture is
then used (with `{folder_id}` + `{access_token}` placeholders substituted
at runtime) by `aurora.uipath_client.publish_maestro_project()` to
publish AURORA's Maestro process headlessly from the VPS.

WHAT THE SCRIPT DOES
--------------------
1. Opens a headed Chromium window pointed at https://cloud.uipath.com/.
2. You log in normally (Auth0, MFA, all the usual flow).
3. You open ANY Maestro / Agentic Process in Studio Web — even a fresh
   "Hello Maestro" you create just for this capture.
4. You click Publish.
5. The script catches the POST and writes the request shape to
   `./publish_request.json` in the directory you ran it from.

WHAT IT WRITES
--------------
A JSON file like:

    {
      "synthetic": false,
      "note": "Captured ...",
      "method": "POST",
      "url_path": "/<account>/studio_/api/...",
      "headers": { ...redacted: bearer → {{UIPATH_ACCESS_TOKEN}}... },
      "body": { ... }
    }

WHAT YOU DO WITH IT
-------------------
1. Open the file in Notepad / VS Code.
2. Copy the full JSON text.
3. Paste it back to me in chat (it has no secrets — bearer + folder id
   are placeholdered).

REQUIREMENTS (one-time setup)
-----------------------------
You need Python 3.11+ on Windows. If you don't have it, install from
https://www.python.org/downloads/windows/. Then in a PowerShell window:

    py -m pip install --upgrade pip
    py -m pip install playwright
    py -m playwright install chromium

Then save THIS file as `capture-publish.py` somewhere (Desktop is fine)
and run:

    py capture-publish.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------- config
START_URL = "https://cloud.uipath.com/"

# Permissive match: anything that looks like a publish call on UiPath's
# domain. We capture EVERY POST/PUT to a writes log too, so if this misses
# the real publish call you can still send the writes log back and we'll
# update the pattern.
PUBLISH_URL_PATTERN = re.compile(
    r"(/studio_/.*publish"
    r"|/studio_/.*projects.*deploy"
    r"|/studio_/api/.*deploy"
    r"|/agentic-process/.*publish"
    r"|/projects?/v[0-9]+/.*publish"
    r"|/projects?/.*/versions"
    r"|UploadPackage)",
    re.IGNORECASE,
)
OUTPUT_PATH = Path.cwd() / "publish_request.json"
WRITES_LOG_PATH = Path.cwd() / "all_writes.log"
TIMEOUT_SECONDS = 600  # 10 minutes; plenty of time to log in + publish
# -----------------------------------------------------------------------


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed in this Python environment.\n"
            "Run these two commands in PowerShell, then re-run this script:\n\n"
            "    py -m pip install playwright\n"
            "    py -m playwright install chromium\n",
            file=sys.stderr,
        )
        sys.exit(1)

    captured: dict | None = None
    all_writes: list[dict] = []  # every POST/PUT for post-mortem if pattern misses

    def on_request(request) -> None:  # type: ignore[no-untyped-def]
        nonlocal captured
        from urllib.parse import urlparse

        if request.method not in {"POST", "PUT", "PATCH"}:
            return

        # Log every write request for diagnosis
        parsed_url = urlparse(request.url)
        if "uipath.com" in parsed_url.netloc or "uipath" in parsed_url.netloc:
            try:
                body_str = request.post_data or ""
                body_preview = body_str[:300] if body_str else ""
            except Exception:
                body_preview = "(unreadable)"
            all_writes.append({
                "method": request.method,
                "url": request.url,
                "path": parsed_url.path,
                "body_size": len(request.post_data or ""),
                "body_preview": body_preview,
            })
            print(f"  [WRITE]  {request.method:4s} {parsed_url.path}")

        if captured is None and PUBLISH_URL_PATTERN.search(request.url):
            try:
                body = request.post_data
                parsed = json.loads(body) if body else {}
            except Exception:
                parsed = {"_raw_body_unparsable": True}

            captured = {
                "synthetic": False,
                "note": "Captured via scripts/windows-capture-publish.py on a live Studio Web session.",
                "method": request.method,
                "url_path": parsed_url.path,
                "url_query": parsed_url.query,
                "headers": _sanitise_headers(dict(request.headers)),
                "body": parsed,
            }
            print(f"  ✓ captured: {request.method} {parsed_url.path}")

    with sync_playwright() as p:
        print("Launching Chromium…")
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        page.on("request", on_request)

        print()
        print("=" * 70)
        print("  STUDIO WEB MAESTRO PUBLISH CAPTURE")
        print("=" * 70)
        print()
        print("Step 1.  A Chromium window just opened at cloud.uipath.com.")
        print("Step 2.  LOG IN to UiPath (your normal Auth0 / MFA flow).")
        print("Step 3.  Open Studio Web (top-right launcher → Studio Web).")
        print("Step 4.  Open ANY Maestro / Agentic Process project.")
        print("         If you have none, click 'Create new project' →")
        print("         'Agentic Process' and accept the defaults.")
        print(f"Step 5.  Click PUBLISH (top right of the Studio Web canvas).")
        print(f"Step 6.  Pick any folder when prompted (AURORA-Demo is ideal).")
        print()
        print(f"This script will wait up to {TIMEOUT_SECONDS // 60} minutes for the")
        print("publish call to fire. As soon as it does, you'll see")
        print("    ✓ captured: POST /...  (followed by the URL)")
        print("and the script will close the browser + write the fixture.")
        print()
        print(f"Output will be written to: {OUTPUT_PATH}")
        print("=" * 70)
        print()

        try:
            page.goto(START_URL, timeout=30000)
        except Exception as e:
            print(f"failed to open {START_URL}: {e}", file=sys.stderr)

        deadline = time.time() + TIMEOUT_SECONDS
        while captured is None and time.time() < deadline:
            try:
                page.wait_for_timeout(1000)
            except Exception:
                break

        browser.close()

    # Always write the writes log — useful even on success for triage.
    if all_writes:
        WRITES_LOG_PATH.write_text(
            json.dumps(all_writes, indent=2) + "\n", encoding="utf-8"
        )
        print(f"  (logged {len(all_writes)} POST/PUT calls → {WRITES_LOG_PATH})")

    if captured is None:
        print(
            f"\n✗ No publish request matching the known patterns within "
            f"{TIMEOUT_SECONDS // 60} minutes.\n"
            f"BUT the writes log captured {len(all_writes)} POST/PUT calls.\n"
            f"  Send me {WRITES_LOG_PATH.name} (or its contents) and I'll\n"
            f"  identify which one is the real publish call and update the\n"
            f"  pattern. The next run will catch it.\n",
            file=sys.stderr,
        )
        sys.exit(2)

    OUTPUT_PATH.write_text(json.dumps(captured, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"✓ Wrote {OUTPUT_PATH}")
    print()
    print("Next: open the file in Notepad / VS Code, copy the FULL content,")
    print("and paste it back into chat. I'll plug it into the publish bridge.")
    print()
    print("Pro tip: the file has no secrets — the bearer token and folder id")
    print("are placeholdered as {{UIPATH_ACCESS_TOKEN}} and {{folder_id}}.")


def _sanitise_headers(headers: dict[str, str]) -> dict[str, str]:
    """Redact bearer + folder id so the fixture is safe to share."""
    out: dict[str, str] = {}
    for k, v in headers.items():
        kl = k.lower()
        if kl == "authorization":
            out[k] = "Bearer {{UIPATH_ACCESS_TOKEN}}"
        elif kl in {"x-uipath-organizationunitid", "x-uipath-organizationunitkey"}:
            out[k] = "{{folder_id}}"
        elif kl == "cookie":
            out[k] = "<<redacted: session cookie removed by capture script>>"
        else:
            out[k] = v
    return out


if __name__ == "__main__":
    main()
