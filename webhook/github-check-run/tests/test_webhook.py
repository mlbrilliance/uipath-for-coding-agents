"""Acceptance tests for the GitHub check_run.completed webhook.

TDD RED phase — these tests define the contract the implementation must satisfy.
"""
from __future__ import annotations

import json

from starlette.testclient import TestClient

from helpers import MaestroMock, make_check_run_payload, sign


def test_good_signature_returns_200_and_posts_to_maestro(
    client: TestClient,
    signed_payload: dict,
    mock_maestro: MaestroMock,
) -> None:
    """POST /github/check-run with valid HMAC + check_run.completed payload
    returns 200 AND posts correlation message to Maestro."""
    response = client.post(
        "/github/check-run",
        content=signed_payload["body"],
        headers=signed_payload["headers"],
    )
    assert response.status_code == 200

    # Maestro should have received GET (instance lookup) + POST (message)
    assert len(mock_maestro.requests) == 2
    assert mock_maestro.requests[0].method == "GET"
    assert mock_maestro.requests[1].method == "POST"


def test_bad_signature_returns_401(
    client: TestClient,
    unsigned_payload: dict,
    mock_maestro: MaestroMock,
) -> None:
    """Tampered or missing X-Hub-Signature-256 header → 401, no Maestro call."""
    response = client.post(
        "/github/check-run",
        content=unsigned_payload["body"],
        headers=unsigned_payload["headers"],
    )
    assert response.status_code == 401
    assert len(mock_maestro.requests) == 0


def test_malformed_json_returns_400(
    client: TestClient,
    secret: str,
    mock_maestro: MaestroMock,
) -> None:
    """Body that isn't JSON → 400 (signature must still verify against the raw
    bytes; 401 takes precedence over 400 if the signature is also bad)."""
    body = b"this is not valid json"
    sig = sign(secret, body)
    response = client.post(
        "/github/check-run",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "check_run",
        },
    )
    assert response.status_code == 400
    assert len(mock_maestro.requests) == 0


def test_unexpected_event_returns_204(
    client: TestClient,
    secret: str,
    mock_maestro: MaestroMock,
) -> None:
    """A check_run with action != 'completed' → 204, no Maestro call."""
    payload = make_check_run_payload(action="created")
    body = json.dumps(payload).encode()
    sig = sign(secret, body)
    response = client.post(
        "/github/check-run",
        content=body,
        headers={
            "X-Hub-Signature-256": sig,
            "X-GitHub-Event": "check_run",
        },
    )
    assert response.status_code == 204
    assert len(mock_maestro.requests) == 0


def test_correlation_post_uses_pr_url_as_key(
    client: TestClient,
    signed_payload: dict,
    mock_maestro: MaestroMock,
) -> None:
    """The outbound Maestro POST URL contains `?key=<pr_url>` and the body
    has the conclusion + check_run_id + html_url + completed_at fields."""
    response = client.post(
        "/github/check-run",
        content=signed_payload["body"],
        headers=signed_payload["headers"],
    )
    assert response.status_code == 200

    post_reqs = [r for r in mock_maestro.requests if r.method == "POST"]
    assert len(post_reqs) == 1

    post_req = post_reqs[0]
    url_str = str(post_req.url)
    assert "key=https%3A%2F%2Fgithub.com%2Faurora-demo-org%2Frepo%2Fpull%2F42" in url_str

    req_body = json.loads(post_req.content)
    assert req_body["conclusion"] == "success"
    assert req_body["check_run_id"] == 123456
    assert "html_url" in req_body
    assert "completed_at" in req_body
