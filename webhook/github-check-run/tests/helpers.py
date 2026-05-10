"""Shared test helpers for the GitHub check_run webhook tests."""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx


def sign(secret: str, body: bytes) -> str:
    """Compute a GitHub webhook HMAC-SHA256 signature."""
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f"sha256={mac.hexdigest()}"


def make_check_run_payload(
    *,
    action: str = "completed",
    conclusion: str = "success",
    check_run_id: int = 123456,
    html_url: str = "https://github.com/aurora-demo-org/repo/runs/123456",
    pr_url: str | None = "https://github.com/aurora-demo-org/repo/pull/42",
    completed_at: str = "2026-05-10T12:00:00Z",
) -> dict[str, Any]:
    prs = [{"html_url": pr_url}] if pr_url else []
    return {
        "action": action,
        "check_run": {
            "id": check_run_id,
            "html_url": html_url,
            "conclusion": conclusion,
            "completed_at": completed_at,
            "pull_requests": prs,
        },
    }


class MaestroMock:
    """Tracks requests to the mock Maestro API for test assertions."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.instance_id: str = "inst-001"

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"value": [{"id": self.instance_id}]},
            )
        return httpx.Response(200, json={"status": "ok"})
