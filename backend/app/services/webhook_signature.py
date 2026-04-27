"""
Webhook signature verification — receiver side (SHARED-CONTRACT.md §7.4).

Header format: `X-Stella-Signature: t=<unix_seconds>,v1=<hex_hmac_sha256>`

Verification (per §7.4):
1. Parse `t` (unix seconds, int) and `v1` (hex HMAC) out of the header.
2. Reject if `|now - t| > 300` seconds — replay window.
3. Compute `HMAC-SHA-256(signing_secret, f"{t}.{raw_body}")`, hex-encoded.
4. `hmac.compare_digest` against the received `v1` (constant-time — never `==`).
5. On any mismatch, return False; the caller responds 401.

The secret is decrypted in memory by the caller (admin endpoint or dispatcher
flow) and passed in as a string. The plaintext never gets logged here even at
DEBUG level — keeps `bash_secret_printing_footgun` discipline alive on the
inbound path too.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time

logger = logging.getLogger("zunkiree.webhook_signature")

REPLAY_WINDOW_SECONDS = 300


class SignatureError(ValueError):
    """Header malformed, missing, or fails verification."""


def _parse_header(header: str) -> tuple[int, str]:
    """Pull `t` and `v1` out of `t=...,v1=...`. Order-insensitive.

    Tolerates whitespace around segments and around `=`. Raises SignatureError
    on any malformation — never lets a malformed header through with a
    "default" timestamp or empty hex (which would let timing or weak-compare
    attacks slip past).
    """
    if not header:
        raise SignatureError("empty signature header")
    parts = [p.strip() for p in header.split(",") if p.strip()]
    fields: dict[str, str] = {}
    for p in parts:
        if "=" not in p:
            raise SignatureError(f"malformed segment: {p!r}")
        k, v = p.split("=", 1)
        fields[k.strip()] = v.strip()
    if "t" not in fields or "v1" not in fields:
        raise SignatureError("missing t or v1 segment")
    try:
        t = int(fields["t"])
    except ValueError as e:
        raise SignatureError(f"t is not an integer: {fields['t']!r}") from e
    v1 = fields["v1"]
    if not v1:
        raise SignatureError("v1 is empty")
    return t, v1


def verify_signature(
    secret: str,
    raw_body: bytes,
    signature_header: str,
    *,
    now: int | None = None,
    replay_window: int = REPLAY_WINDOW_SECONDS,
) -> bool:
    """Return True iff the header is valid for `raw_body` under `secret`.

    `now` is overridable for tests. Default is `time.time()`. `raw_body`
    MUST be the exact bytes of the HTTP request body — not a re-serialized
    JSON object. The endpoint reads raw bytes via `await request.body()`
    BEFORE any JSON parsing.
    """
    if not secret:
        # Don't compute a placeholder HMAC against an empty secret; that would
        # make the receiver trivially spoofable for any tenant whose creds row
        # lost its webhook_signing_secret_encrypted column value.
        logger.warning("verify_signature called with empty secret — denying")
        return False
    try:
        t, received_hex = _parse_header(signature_header)
    except SignatureError as e:
        logger.info("signature header malformed: %s", e)
        return False

    current = int(now) if now is not None else int(time.time())
    if abs(current - t) > replay_window:
        logger.info(
            "signature outside replay window: |now=%s - t=%s| > %ds",
            current, t, replay_window,
        )
        return False

    signed_payload = f"{t}.".encode("utf-8") + raw_body
    expected_hex = hmac.new(
        secret.encode("utf-8"), signed_payload, hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_hex, received_hex)
