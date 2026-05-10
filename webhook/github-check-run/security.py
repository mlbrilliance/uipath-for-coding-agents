"""HMAC-SHA256 verification for GitHub webhook signatures."""
from __future__ import annotations

import hashlib
import hmac


def verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Constant-time HMAC-SHA256 verification of GitHub webhook signature.

    The signature header has the form ``sha256=<hex>``.  Verification uses
    :func:`hmac.compare_digest` to prevent timing attacks.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    received = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, received)
