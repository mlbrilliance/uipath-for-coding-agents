# Test Manager Linkage Runbook

Test Manager has **no documented "publish a test set" write API**. The
supported flow is:

1. `uipath pack && uipath publish` → Studio publishes the test package to
   Orchestrator.
2. **Test Manager links** the published package to existing test cases
   via the documented Select-Automation linkage call. This is a *sync*,
   not a *publish*.

`lib/aurora/test_manager.py` automates step 2. This runbook is for when
the API rotates and we need to re-capture the new shape.

## Architecture

```
                    ┌────────────────────────────┐
                    │  TestManagerClient         │
                    │  .link_automation()        │
                    └─────────────┬──────────────┘
                                  │
                  ┌───────────────┴────────────────┐
                  ▼                                ▼
    ┌──────────────────────────┐   ┌────────────────────────────┐
    │  PRIMARY (HTTP)          │   │  FALLBACK (Playwright)     │
    │  POST                    │   │  Drives Test Manager       │
    │  /test_/api/v1/.../link  │   │  "Select Automation" UI    │
    └──────────────────────────┘   └────────────────────────────┘
```

### Primary rail — HTTP

`TestManagerClient.link_automation(test_case_id, package_id, entry_point)`
POSTs to `/test_/api/v1/testCases/{test_case_id}/automations/link` with a
JSON body of `{testCaseId, packageId, entryPoint}` and returns a
`LinkResult` (`link_id`, `linked`).

Conventions:

- **R.E.01** — try/except wraps the HTTP call.
- **R.E.02** — 5xx → retry up to 3× with exponential backoff (base 5s).
- **R.E.03** — 4xx → `BusinessError`, never retried.
- **R.K.01** — `_build_link_request` and `_parse_link_response` are pure
  helpers, no I/O, easy to unit-test.
- **R.K.06** — idempotent: re-invocation with the same
  `(test_case_id, package_id)` returns the cached `LinkResult` without
  re-POSTing.
- **R.X.05** — `UIPATH_ACCESS_TOKEN` is read from env (minted by
  `aurora-auth`); never hard-coded.

### Fallback rail — Playwright

`aurora.playwright.test_manager_ui.link_via_ui(...)` opens Chromium,
navigates to the test case's Test Manager page, clicks "Select
Automation", and intercepts the resulting `/test_/api/v1/...link...`
network response to extract the link id.

This rail is for human-in-the-loop / Operate use only. Do **not** call it
from CI — the API rail is primary.

## When the API rotates — re-capturing the shape

UiPath occasionally rotates internal API paths. Symptom: the primary rail
returns a 404 from `/test_/api/v1/...`. Steps to recover:

1. **Confirm rotation, not outage**

   ```bash
   curl -i -H "Authorization: Bearer $UIPATH_ACCESS_TOKEN" \
     "$UIPATH_URL/../test_/api/v1/testCases?\$top=1"
   ```

   If 404 with a JSON body that doesn't look like Test Manager's, it's a
   path rotation. If 503 / 502 / network errors, it's an outage — keep
   retrying instead.

2. **Use the UI fallback** to keep the Operate fleet linking in the
   meantime:

   ```python
   from aurora.playwright.test_manager_ui import link_via_ui
   link_via_ui(
       test_case_id="TC-1",
       package_id="MyPackage",
       entry_point="Main.xaml",
   )
   ```

3. **Capture the new API shape** with a request inspector. Open
   Chromium with DevTools, navigate to the test case in Test Manager,
   click "Select Automation", complete the linkage manually, and copy
   the captured `Request URL`, `Request Method`, `Request Headers`, and
   `Request Body` from the Network tab.

4. **Update the constants** in `lib/aurora/test_manager.py`:

   - `TEST_MANAGER_API_PATH_PREFIX` — typically `/test_/api/v1` but may
     change.
   - `_build_link_request.url_path` — the path template
     (`/testCases/{test_case_id}/automations/link` today).
   - The body keys (`testCaseId`, `packageId`, `entryPoint`) — rename if
     the new shape uses different names.

5. **Update the unit-test URL regexes** in
   `tests/unit/test_test_manager.py` (`LIST_URL_RE`, `LINK_URL_RE`,
   `ANY_TM_URL_RE`) to match the new shape.

6. **Run the integration test live** with
   `UIPATH_INTEGRATION=1 UIPATH_TM_PROJECT_KEY=DEMO uv run pytest
   tests/integration/test_tester_live.py -v` against a sandbox project.

7. **Commit** as `T-E? [docs]: re-capture test-manager linkage shape`.

## Idempotency contract

`link_automation` is idempotent on `(test_case_id, package_id)`:

- First call → POST to API → cache `LinkResult` keyed by
  `(test_case_id, package_id)` → return.
- Second call with same key → return cached `LinkResult` without
  re-POSTing.

This makes the Operate fleet's replay-after-failure safe: re-running the
linkage step after a partial failure is a no-op for already-linked
cases. If you need to *force* a re-link (e.g. the package was rebuilt
under the same id), construct a fresh `TestManagerClient` to clear the
cache.

## Error handling matrix

| HTTP status | Behaviour                                      | Convention |
| ----------- | ---------------------------------------------- | ---------- |
| 2xx         | Parse via `_parse_link_response` → `LinkResult`| —          |
| 4xx         | Raise `BusinessError` immediately, no retry    | R.E.03     |
| 5xx         | Retry up to 3× with exponential backoff (5s)   | R.E.02     |
| Network     | Retry up to 3× with exponential backoff        | R.E.01     |

## Why this exists

Captured in `docs/grill-2026-05-09.md §Contradicted #5`: the original
draft of `agents/tester.md` claimed the Tester "publishes test sets via
the Test Manager API." That claim is false — the Test Manager API is
read/sync-oriented, not write-oriented. T-E1 corrects the agent's
description and ships the runtime support library for the actual
documented flow (publish to Orchestrator → link via Test Manager).
