"""
Unit tests for the HMAC signature verifier (SHARED-CONTRACT.md §7.4).

Pure helper — no DB, no FastAPI. Each test exercises one branch of
verify_signature so the failure mode is immediately readable from the test
name. Constant-time comparison is asserted via hmac.compare_digest's own
behavior (we don't time-test in unit; the helper just has to call it).
"""
from __future__ import annotations

import hashlib
import hmac
import time

from app.services.webhook_signature import verify_signature


def _sign(secret: str, body: bytes, t: int) -> str:
    sig = hmac.new(secret.encode("utf-8"), f"{t}.".encode("utf-8") + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def test_valid_signature_passes():
    secret = "whsec_abcdef0123456789"
    body = b'{"id":"evt_1","event":"product.updated"}'
    t = int(time.time())
    header = _sign(secret, body, t)
    assert verify_signature(secret, body, header) is True


def test_tampered_body_fails():
    secret = "whsec_abcdef0123456789"
    body = b'{"id":"evt_1","event":"product.updated"}'
    t = int(time.time())
    header = _sign(secret, body, t)
    tampered = body + b" "  # one extra byte invalidates the HMAC
    assert verify_signature(secret, tampered, header) is False


def test_wrong_secret_fails():
    body = b'{"id":"evt_1"}'
    t = int(time.time())
    header = _sign("whsec_real", body, t)
    assert verify_signature("whsec_attacker_guess", body, header) is False


def test_stale_timestamp_outside_window_fails():
    """`|now - t| > 300` must reject. Picked t = now - 301 to fall just past."""
    secret = "whsec_abc"
    body = b'{"x":1}'
    now = int(time.time())
    t = now - 301
    header = _sign(secret, body, t)
    assert verify_signature(secret, body, header, now=now) is False


def test_future_timestamp_outside_window_fails():
    """Symmetric: a clock-skewed-forward t > now+300 also rejected."""
    secret = "whsec_abc"
    body = b'{"x":1}'
    now = int(time.time())
    t = now + 301
    header = _sign(secret, body, t)
    assert verify_signature(secret, body, header, now=now) is False


def test_just_inside_window_passes():
    """Boundary: |now - t| == 300 is still inside the window."""
    secret = "whsec_abc"
    body = b'{"x":1}'
    now = int(time.time())
    t = now - 300
    header = _sign(secret, body, t)
    assert verify_signature(secret, body, header, now=now) is True


def test_malformed_header_missing_t_fails():
    secret = "whsec_abc"
    body = b'{"x":1}'
    header = "v1=abc123"  # no t
    assert verify_signature(secret, body, header) is False


def test_malformed_header_missing_v1_fails():
    secret = "whsec_abc"
    body = b'{"x":1}'
    header = f"t={int(time.time())}"  # no v1
    assert verify_signature(secret, body, header) is False


def test_empty_header_fails():
    assert verify_signature("whsec_abc", b'{}', "") is False


def test_empty_secret_denies():
    """Defensive: never compute an HMAC against empty secret. A missing-secret
    state on the credentials row must NOT silently authenticate any caller."""
    t = int(time.time())
    body = b'{"x":1}'
    # Even if the attacker computes a "valid" header against an empty secret,
    # we refuse to verify when secret is empty.
    header = _sign("", body, t)
    assert verify_signature("", body, header) is False


def test_segments_can_be_in_any_order():
    """Header is comma-separated key=value; order is not specified by the
    contract. We tolerate v1=...,t=... as well as t=...,v1=..."""
    secret = "whsec_abc"
    body = b'{"x":1}'
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    header = f"v1={sig},t={t}"
    assert verify_signature(secret, body, header) is True
