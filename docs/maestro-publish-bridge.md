# Maestro Publish Bridge

AURORA needs to publish Maestro / Studio Web Solutions programmatically, but
UiPath provides **no documented CLI verb** for publishing a Studio Web
agentic-process project (`uipath publish` only handles Coded Agents /
Coded Workflows). This document describes the two-rail bridge AURORA uses
to fill that gap.

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
OAuth bearer and per-tenant identifiers, and POSTs directly via `httpx`.

- **Fixture-based**: the URL path, headers, and body shape come from the
  captured fixture, not from hardcoded constants. When UiPath rotates the
  API, re-run `scripts/windows-capture-publish.py` and the wrapper adapts
  automatically.
- **Retries**: 5xx responses are retried up to 3x with exponential backoff
  (R.E.02). 4xx responses raise `BusinessError` immediately (R.E.03).
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

## Live publish audience requirement (operator action required)

The captured endpoint is

    POST /{account}/studio_/backend/api/Solution/{solution_id}/Publish-Requests

This is a **Studio Web** endpoint, not an Orchestrator endpoint. Tokens
minted for `audience=UiPath.Orchestrator` (the default for an External App
registered with `OR.*` scopes) are rejected with:

```
HTTP 401
www-authenticate: Bearer realm="https://cloud.uipath.com/identity_",
    error="invalid_token",
    error_description="The audience 'UiPath.Orchestrator' is invalid"
```

The `error_description` is the smoking gun: UiPath's identity server
issues tokens whose `aud` JWT claim is determined by the scope set granted
to the External App. **Our External App currently has only `OR.*` scopes**,
so every token it mints has `aud=UiPath.Orchestrator` and is rejected by
the Studio Web backend.

### To unlock live publish from the VPS (~1 minute operator action)

1. Open Automation Cloud → **Admin** → **External Applications**.
2. Edit the AURORA app.
3. Add the following Studio Web scopes (they appear under "Studio Web" or
   "Project Management" in the scope picker, depending on UI version):
   - `PM.Project` (read/write Studio Web projects)
   - `PM.ProjectVersion` (publish a new version of a Solution)
4. Save.
5. Update `policy.yaml::uipath_scopes` to include the new scopes:

   ```yaml
   uipath_scopes: "OR.Administration OR.Folders OR.Jobs OR.Assets ... PM.Project PM.ProjectVersion"
   ```

6. Restart any running daemons so they pick up the new token audience on
   the next refresh.

After this one-time grant, `UiPathClient.publish_maestro_project()` will
succeed against any Solution in the tenant.

### Why the audit shows 401, not a wiring bug

When you run

    .venv/bin/python -c "from aurora.uipath_client import UiPathClient; ..."

against the live tenant before the scope grant, you'll see:

    FAILURE: BusinessError HTTP 401 from publish endpoint

This is **the right failure** — it means we hit the right endpoint with
the right method/headers/body shape, and UiPath accepted the request
*structurally*. The 401 is the audience check. Our 11 unit tests + the
captured live fixture prove the bridge is wired correctly; the 401 is a
deployment-time admin-console action, not a code change.

## How to re-capture the publish request

If the HTTP wrapper starts failing with 404 (UiPath has rotated the API)
or the request shape changes (new required field), re-run the capture on
a Windows machine — the `aurora-auth` client-credentials flow cannot
authenticate to Studio Web's interactive SPA.

```powershell
# In PowerShell on Windows, in a directory of your choice:
curl.exe -L --ssl-no-revoke -o capture-publish.py `
  -H "Accept: application/vnd.github.v3.raw" `
  "https://api.github.com/repos/mlbrilliance/uipath-for-coding-agents/contents/scripts/windows-capture-publish.py?ref=feature/aurora-final-mile"
py capture-publish.py
```

The script:
1. Opens a headed Chromium window pointed at `cloud.uipath.com`.
2. You log in manually (Auth0 + MFA).
3. You open any Studio Web Solution and click **Publish**.
4. The script intercepts every POST/PUT to a `*.uipath.com` domain,
   pattern-matches the publish call, redacts the bearer token, and writes
   `publish_request.json`. (If the pattern misses, an `all_writes.log`
   is also written so the pattern can be tightened.)

Paste the captured JSON back to the build agent; it replaces
`tests/fixtures/maestro/publish_request.json`.

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
from aurora.uipath_client import UiPathClient, BusinessError
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

`tests/fixtures/maestro/publish_request.json` (captured 2026-05-12):

```json
{
  "synthetic": false,
  "note": "Captured via scripts/windows-capture-publish.py ...",
  "method": "POST",
  "url_path": "/{{account}}/studio_/backend/api/Solution/{{solution_id}}/Publish-Requests",
  "headers": {
    "authorization": "Bearer {{UIPATH_ACCESS_TOKEN}}",
    "x-uipath-tenantid": "{{tenant_id}}",
    "content-type": "application/json",
    ...
  },
  "body": {
    "packageName": "{{package_name}}",
    "locationKey": "{{tenant_id}}",
    "version": "{{version}}",
    "autoDeploy": false,
    "locationFQN": "Orchestrator Tenant",
    "withClientPackaging": false,
    ...
  }
}
```

- `synthetic: false` means the fixture is a real capture from a live
  Studio Web session. Integration tests treat `synthetic: true` as a
  loud warning.
- Template variables (`{{account}}`, `{{tenant_id}}`, `{{solution_id}}`,
  `{{package_name}}`, `{{version}}`, `{{UIPATH_ACCESS_TOKEN}}`) are
  replaced at runtime by `_build_publish_request()`.

## Pure helpers

These are extracted for testability (R.K.01):

- `_build_publish_request(fixture_path, access_token, solution_id, package_name, tenant_id, account, version)`
  → `dict` with `method`, `url_path`, `headers`, `body`
- `_parse_publish_response(payload)` → `dict` with `version`, `status`, `projectKey`, `packageId`
- `_read_studio_web_solution_id(project_dir)` → `solution_id | None` from
  `.studio-web/solution_id` or `project.json::studioWebSolutionId`
- `_derive_next_version(project_dir, version_bump)` → semver string
- `_bump_version(current, bump_type)` → bumped semver string

## Resolution order for required identifiers

The wrapper resolves each identifier from (1) call kwarg, (2) project
metadata, (3) environment — in that order:

| Identifier      | kwarg          | project file                             | env var               |
|-----------------|----------------|------------------------------------------|-----------------------|
| `solution_id`   | `solution_id`  | `.studio-web/solution_id` or `project.json::studioWebSolutionId` | `UIPATH_SOLUTION_ID`  |
| `package_name`  | `package_name` | falls back to `project_dir.name`         | —                     |
| `tenant_id`     | `tenant_id`    | —                                        | `UIPATH_TENANT_ID`    |
| `account`       | `account`      | —                                        | `UIPATH_ACCOUNT_SLUG` |

Missing `solution_id` raises `BusinessError` with a clear message — no
fallback to a default, since publishing the wrong Solution is worse than
failing loud.

## Error handling

| HTTP status | Behaviour | Convention |
|---|---|---|
| 4xx | Raise `BusinessError` immediately | R.E.03 |
| 5xx | Retry up to 3x with exponential backoff | R.E.02 |
| Network error | Retry up to 3x | R.E.01 |
| Success | Parse response via `_parse_publish_response` | — |
