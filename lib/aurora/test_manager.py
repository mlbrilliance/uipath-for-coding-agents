"""Test Manager linkage bridge.

Test Manager has no documented "publish a test set" write API. The
supported flow is:

    1. ``uipath pack`` — Studio packs the test project.
    2. ``uipath publish`` — package goes to Orchestrator.
    3. **Test Manager LINKS the published package** to existing test
       cases via the Select-Automation linkage endpoint.

This module is rail #3. It mirrors the HTTP-wrapper shape of
``UiPathClient.publish_maestro_project`` (T-D3): try/catch around the HTTP
boundary, exponential backoff on 5xx (R.E.02), surface 4xx as
``BusinessError`` (R.E.03), idempotent under repeat (R.K.06), pure
helpers for request/response shaping (R.K.01).

The Playwright fallback for when the API rotates lives in
``aurora.playwright.test_manager_ui``.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, cast

import httpx

from aurora.uipath_client import BusinessError

logger = logging.getLogger(__name__)

TEST_MANAGER_API_PATH_PREFIX = "/test_/api/v1"
LINK_MAX_RETRIES = 3
LINK_RETRY_BASE_DELAY = 5.0  # seconds; per R.E.02 (≥ 5s)
LINK_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class TestCase:
    """A Test Manager test case projection."""

    id: str
    name: str
    project_key: str


@dataclass(frozen=True)
class LinkResult:
    """Outcome of an automation-linkage call."""

    link_id: str
    linked: bool


class TestManagerClient:
    """Sync linkage client for Test Manager.

    Public surface:
        - ``list_test_cases(project_key)`` — returns ``list[TestCase]``
        - ``link_automation(test_case_id, package_id, entry_point)``
          → ``LinkResult``

    The client is constructed with no required arguments; it reads
    ``UIPATH_URL`` and ``UIPATH_ACCESS_TOKEN`` from the environment per
    R.X.05 (token minted by aurora-auth, not hard-coded). ``folder_id``
    is optional; when set, every request includes the
    ``X-UIPATH-OrganizationUnitId`` header.
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        folder_id: int | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.url = url or os.environ.get("UIPATH_URL")
        if not self.url:
            raise RuntimeError("UIPATH_URL not set")
        self.folder_id = folder_id
        self.timeout_seconds = timeout_seconds or LINK_TIMEOUT_SECONDS
        self._link_cache: dict[tuple[str, str], LinkResult] = {}

    # ---------- URL & header plumbing ----------

    def _base_url(self) -> str:
        base = str(self.url).rstrip("/")
        if base.endswith("/orchestrator_"):
            base = base[: -len("/orchestrator_")]
        return base

    def _access_token(self) -> str:
        return os.environ.get("UIPATH_ACCESS_TOKEN", "")

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.folder_id is not None:
            headers["X-UIPATH-OrganizationUnitId"] = str(self.folder_id)
        return headers

    # ---------- list_test_cases ----------

    def list_test_cases(self, project_key: str) -> list[TestCase]:
        """List test cases for a Test Manager project.

        Uses the documented OData-shaped surface at
        ``/test_/api/v1/testCases?$filter=ProjectKey eq '<key>'``.
        """
        url = f"{self._base_url()}{TEST_MANAGER_API_PATH_PREFIX}/testCases"
        params = {"$filter": f"ProjectKey eq '{project_key}'"}
        try:
            response = httpx.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise RuntimeError(f"test-manager list_test_cases network error: {exc}") from exc

        if response.status_code >= 400:
            raise BusinessError(
                f"HTTP {response.status_code} from list_test_cases: {response.text[:200]}"
            )
        payload = response.json()
        return _parse_test_case_list(payload)

    # ---------- link_automation ----------

    def link_automation(
        self,
        *,
        test_case_id: str,
        package_id: str,
        entry_point: str,
    ) -> LinkResult:
        """Link a published Orchestrator package to a Test Manager test case.

        Idempotent (R.K.06): re-invocation with the same
        ``(test_case_id, package_id)`` returns the cached ``LinkResult``
        without re-POSTing.
        """
        cache_key = (test_case_id, package_id)
        if cache_key in self._link_cache:
            logger.info(
                "link_automation: cached link for (%s, %s); skipping POST",
                test_case_id,
                package_id,
            )
            return self._link_cache[cache_key]

        spec = _build_link_request(
            access_token=self._access_token(),
            folder_id=self.folder_id,
            test_case_id=test_case_id,
            package_id=package_id,
            entry_point=entry_point,
        )
        full_url = f"{self._base_url()}{spec['url_path']}"
        result = self._post_with_retry(full_url=full_url, spec=spec)
        self._link_cache[cache_key] = result
        return result

    # ---------- internal: POST with retry ----------

    def _post_with_retry(
        self,
        *,
        full_url: str,
        spec: dict[str, Any],
    ) -> LinkResult:
        last_exc: Exception | None = None
        for attempt in range(LINK_MAX_RETRIES):
            try:
                response = httpx.post(
                    full_url,
                    headers=spec["headers"],
                    json=spec["body"],
                    timeout=self.timeout_seconds,
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                logger.warning(
                    "link_automation attempt %d network error: %s", attempt + 1, exc
                )
                if attempt < LINK_MAX_RETRIES - 1:
                    time.sleep(LINK_RETRY_BASE_DELAY * (2**attempt))
                continue

            if 400 <= response.status_code < 500:
                # R.E.03 — never retry 4xx
                raise BusinessError(
                    f"HTTP {response.status_code} from test-manager link: "
                    f"{response.text[:200]}"
                )

            if response.status_code >= 500:
                last_exc = RuntimeError(
                    f"HTTP {response.status_code} from test-manager link"
                )
                logger.warning(
                    "link_automation attempt %d got %d", attempt + 1, response.status_code
                )
                if attempt < LINK_MAX_RETRIES - 1:
                    time.sleep(LINK_RETRY_BASE_DELAY * (2**attempt))
                continue

            return _parse_link_response(response.json())

        raise last_exc or RuntimeError("link_automation failed after retries")


# ---------------------------------------------------------------------------
# Pure helpers (R.K.01 — no I/O, easy to unit-test)
# ---------------------------------------------------------------------------


def _build_link_request(
    *,
    access_token: str,
    folder_id: int | None,
    test_case_id: str,
    package_id: str,
    entry_point: str,
) -> dict[str, Any]:
    """Build the request spec for a link_automation POST.

    Returns a dict with ``method``, ``url_path``, ``headers``, ``body``.
    No I/O — purely shapes the request from inputs.
    """
    headers: dict[str, str] = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if folder_id is not None:
        headers["X-UIPATH-OrganizationUnitId"] = str(folder_id)

    url_path = (
        f"{TEST_MANAGER_API_PATH_PREFIX}/testCases/{test_case_id}/automations/link"
    )
    body: dict[str, Any] = {
        "testCaseId": test_case_id,
        "packageId": package_id,
        "entryPoint": entry_point,
    }
    return {
        "method": "POST",
        "url_path": url_path,
        "headers": headers,
        "body": body,
    }


def _parse_link_response(payload: dict[str, Any]) -> LinkResult:
    """Project the link-response payload into a ``LinkResult``."""
    return LinkResult(
        link_id=str(payload.get("linkId") or payload.get("id") or ""),
        linked=bool(payload.get("linked", payload.get("alreadyLinked", False))),
    )


def _parse_test_case_list(payload: dict[str, Any]) -> list[TestCase]:
    """Project a list payload (``{"value": [...]}``) into ``TestCase`` rows."""
    rows = cast(list[dict[str, Any]], payload.get("value", []))
    return [
        TestCase(
            id=str(row.get("Id") or row.get("id", "")),
            name=str(row.get("Name") or row.get("name", "")),
            project_key=str(row.get("ProjectKey") or row.get("projectKey", "")),
        )
        for row in rows
    ]
