# Maestro Publish Bridge

AURORA needs to publish Maestro processes programmatically, but UiPath
provides **no documented CLI verb** for publishing a Studio Web Maestro
project (`uipath publish` only handles Coded Agents / Coded Workflows).
This document describes the two-rail bridge AURORA uses to fill that gap.

## Architecture

```
                    ┌───────────────────────┐
                    │  UiPathClient         │
                    │  .publish_maestro_    │
                    │   project()           │
                    └───────┬───────────────┘
                            │
                ┌───────────┴───────────┐
                ▼                       ▼
    ┌───────────────────┐   ┌───────────────────────┐
    │  PRIMARY (HTTP)   │   │  FALLBACK (Playwright)│
    │  Replays captured │   │  Drives Studio Web    │
    │  Studio Web POST  │   │  "Publish" button     │
    └───────────────────┘   └───────────────────────┘
```

### Primary rail: HTTP-API wrapper

`UiPathClient.publish_maestro_project()` reads the captured request shape
from `tests/fixtures/maestro/publish_request.json`, substitutes the live
OAuth bearer and folder ID, and POSTs directly via `httpx`.

- **Fixture-based**: the URL path, headers, and body shape come from the
  captured fixture, not from hardcoded constants. When UiPath changes the
  API, re-run the capture tool and the wrapper adapts automatically.
- **Retries**: 5xx responses are retried up to 3x with exponential backoff
  (R.E.02). 4xx responses raise `BusinessException` immediately (R.E.03).
- **Token**: reads `UIPATH_ACCESS_TOKEN` from the environment, minted by
  the `aurora-auth` skill (R.X.05).

### Fallback rail: Playwright UI drive

`aurora.playwright.publish_ui_fallback.publish_via_ui()` opens a real
Chromium browser, navigates to Studio Web, and clicks the "Publish"
button. This is used when the HTTP API has rotated and the primary rail
fails with a 404 or unexpected response shape.

- **Not for CI**: the fallback opens a browser; it's for the Operate fleet
  or manual use behind a feature flag.
- **Response capture**: the fallback intercepts the network response to
  extract the published version, so it returns the same shape as the
  primary rail.

## How to re-capture the publish request

If the HTTP wrapper starts failing (typically 404 on the publish endpoint),
UiPath has likely rotated the API. Re-capture:

```bash
# 1. Set the required environment variables
export UIPATH_ACCOUNT_SLUG=your-account
export UIPATH_TENANT_SLUG=your-tenant

# 2. Run the capture tool (opens a browser — human must log in)
uv run python -m aurora.playwright.capture

# 3. The tool writes the captured request to:
#    tests/fixtures/maestro/publish_request.json
#    (with the live token sanitised to {{UIPATH_ACCESS_TOKEN}})
```

The capture tool:
1. Opens `https://cloud.uipath.com/<account>/<tenant>/studio_web/` in a
   non-headless Chromium window.
2. **You log in manually** — do not automate this step.
3. You select the Maestro project and click "Publish".
4. The tool intercepts the network request matching `/studio_/api/publish`,
   captures the URL path, headers, and body, sanitises the bearer token,
   and writes the fixture.

After re-capturing, the synthetic flag in the fixture is set to `false`,
and the integration test will use the real shape.

## Swapping rails on demand

The primary rail is used by default. To force the fallback:

```python
from aurora.playwright.publish_ui_fallback import publish_via_ui

result = publish_via_ui(
    project_dir=Path("/path/to/maestro-project"),
    version_bump="patch",
)
```

Or wrap both with automatic fallback:

```python
from aurora.uipath_client import UiPathClient, BusinessException
from aurora.playwright.publish_ui_fallback import publish_via_ui

client = UiPathClient(folder="AURORA-Demo")
try:
    result = client.publish_maestro_project(
        project_dir=project_dir,
        version_bump="patch",
    )
except BusinessError:
    # HTTP rail failed — fall back to UI
    result = publish_via_ui(
        project_dir=project_dir,
        version_bump="patch",
    )
```

## Fixture format

`tests/fixtures/maestro/publish_request.json`:

```json
{
  "synthetic": false,
  "note": "Captured via lib/aurora/playwright/capture.py",
  "method": "POST",
  "url_path": "/studio_/api/publish",
  "headers": {
    "Authorization": "Bearer {{UIPATH_ACCESS_TOKEN}}",
    "X-UIPATH-OrganizationUnitId": "{{folder_id}}",
    "Content-Type": "application/json"
  },
  "body": {
    "projectKey": "{{project_key}}",
    "version": "{{version}}",
    "versionBump": "patch",
    "projectFiles": [],
    "isLatest": true
  }
}
```

- `synthetic: true` means the fixture was hand-crafted, not captured.
  Integration tests should fail loudly if the fixture is synthetic.
- Template variables (`{{UIPATH_ACCESS_TOKEN}}`, `{{folder_id}}`) are
  replaced at runtime by `_build_publish_request()`.

## Pure helpers

These are extracted for testability (R.K.01):

- `_build_publish_request(fixture_path, access_token, folder_id, project_key, version, version_bump)`
  → `dict` with `method`, `url_path`, `headers`, `body`
- `_parse_publish_response(payload)` → `dict` with `version`, `status`, `projectKey`, `packageId`
- `_derive_next_version(project_dir, version_bump)` → semver string
- `_bump_version(current, bump_type)` → bumped semver string

## Error handling

| HTTP status | Behaviour | Convention |
|---|---|---|
| 4xx | Raise `BusinessError` immediately | R.E.03 |
| 5xx | Retry up to 3x with exponential backoff | R.E.02 |
| Network error | Retry up to 3x | R.E.01 |
| Success | Parse response via `_parse_publish_response` | — |
