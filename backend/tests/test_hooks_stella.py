"""
Endpoint tests for `POST /api/v1/hooks/stella/{site_id}`.

Per Z3 byte-identical-test discipline:
- Status-code-only assertions for 401 / 400 (we haven't locked a body shape).
- Dedup is asserted by counting calls into `insert_event_idempotent`, not by
  hitting a real DB — the helper itself is unit-tested via SQL pattern.
- We mock the DB session and the dispatcher's insert helper at the seam so
  these tests stay fast and don't require a live Postgres.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.hooks_stella import router as hooks_stella_router


SECRET = "whsec_test_0123456789abcdef"


def _sign(secret: str, body: bytes, t: int | None = None) -> str:
    t = int(time.time()) if t is None else t
    sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def _envelope(*, event_id="evt_test_1", event="product.updated", site_id="kasa") -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "event": event,
            "version": "1",
            "occurred_at": "2026-04-27T00:00:00Z",
            "delivery_attempt": 1,
            "merchant": {"id": str(uuid.uuid4()), "site_id": site_id},
            "correlation_id": str(uuid.uuid4()),
            "data": {"id": "p1", "name": "Tee"},
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _make_client(
    *,
    customer=None,
    creds=None,
    insert_returns: bool = True,
):
    """Build a TestClient with the hooks_stella router and the DB seam mocked.

    `customer` and `creds` are the rows looked up by site_id; pass None to
    simulate "not found". `insert_returns` mirrors `insert_event_idempotent`'s
    return value (True = newly inserted, False = dedup hit).
    """
    app = FastAPI()
    app.include_router(hooks_stella_router, prefix="/api/v1")

    fake_db = AsyncMock()

    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    creds_result = MagicMock()
    creds_result.scalar_one_or_none.return_value = creds
    fake_db.execute.side_effect = [customer_result, creds_result]

    async def fake_get_db():
        yield fake_db

    from app.database import get_db
    app.dependency_overrides[get_db] = fake_get_db

    insert_mock = AsyncMock(return_value=insert_returns)
    decrypt_patch = patch("app.api.hooks_stella.decrypt", lambda _: SECRET)
    insert_patch = patch("app.api.hooks_stella.insert_event_idempotent", insert_mock)
    decrypt_patch.start()
    insert_patch.start()

    client = TestClient(app)
    client._patches = (decrypt_patch, insert_patch)  # type: ignore[attr-defined]
    client._insert_mock = insert_mock  # type: ignore[attr-defined]
    return client


def _teardown(client):
    for p in client._patches:
        p.stop()


def _customer(site_id="kasa"):
    c = MagicMock()
    c.id = uuid.uuid4()
    c.site_id = site_id
    return c


def _creds(remote_site_id="kasa"):
    c = MagicMock()
    c.customer_id = uuid.uuid4()
    c.backend_type = "stella"
    c.remote_site_id = remote_site_id
    c.is_active = True
    c.webhook_signing_secret_encrypted = "ciphertext-blob"
    return c


def test_valid_signature_returns_200_and_inserts():
    customer = _customer()
    creds = _creds(remote_site_id="kasa")
    client = _make_client(customer=customer, creds=creds, insert_returns=True)
    try:
        body = _envelope()
        r = client.post(
            "/api/v1/hooks/stella/kasa",
            content=body,
            headers={"X-Stella-Signature": _sign(SECRET, body), "Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert client._insert_mock.await_count == 1
    finally:
        _teardown(client)


def test_duplicate_event_returns_200_with_no_extra_processing():
    """Dedup hit (insert_event_idempotent returns False) is still a 200 to
    Stella per SHARED-CONTRACT §7.5 at-least-once contract."""
    customer = _customer()
    creds = _creds(remote_site_id="kasa")
    client = _make_client(customer=customer, creds=creds, insert_returns=False)
    try:
        body = _envelope()
        r = client.post(
            "/api/v1/hooks/stella/kasa",
            content=body,
            headers={"X-Stella-Signature": _sign(SECRET, body), "Content-Type": "application/json"},
        )
        assert r.status_code == 200
    finally:
        _teardown(client)


def test_tampered_signature_returns_401():
    customer = _customer()
    creds = _creds(remote_site_id="kasa")
    client = _make_client(customer=customer, creds=creds)
    try:
        body = _envelope()
        # Sign the body, then mutate the body so the signature no longer matches.
        sig = _sign(SECRET, body)
        r = client.post(
            "/api/v1/hooks/stella/kasa",
            content=body + b" ",
            headers={"X-Stella-Signature": sig, "Content-Type": "application/json"},
        )
        assert r.status_code == 401
    finally:
        _teardown(client)


def test_site_id_mismatch_returns_401():
    """envelope.merchant.site_id != stored remote_site_id is 401, not 400.
    Defends against mis-routed deliveries leaking across tenants."""
    customer = _customer(site_id="kasa")
    creds = _creds(remote_site_id="kasa-stella")  # different from envelope's "kasa"
    client = _make_client(customer=customer, creds=creds)
    try:
        body = _envelope(site_id="kasa")
        r = client.post(
            "/api/v1/hooks/stella/kasa",
            content=body,
            headers={"X-Stella-Signature": _sign(SECRET, body), "Content-Type": "application/json"},
        )
        assert r.status_code == 401
    finally:
        _teardown(client)


def test_unknown_site_id_returns_401_not_404():
    """Unknown tenant returns 401 (same response shape as signature mismatch)
    so attackers can't enumerate tenants via 404 vs 401."""
    client = _make_client(customer=None, creds=None)
    try:
        body = _envelope()
        r = client.post(
            "/api/v1/hooks/stella/does-not-exist",
            content=body,
            headers={"X-Stella-Signature": _sign(SECRET, body), "Content-Type": "application/json"},
        )
        assert r.status_code == 401
    finally:
        _teardown(client)


def test_no_creds_or_no_signing_secret_returns_401():
    """Tenant exists but has no backend creds (or creds without webhook secret)
    → still 401 (no oracle for tenant existence)."""
    customer = _customer()
    client = _make_client(customer=customer, creds=None)
    try:
        body = _envelope()
        r = client.post(
            "/api/v1/hooks/stella/kasa",
            content=body,
            headers={"X-Stella-Signature": _sign(SECRET, body), "Content-Type": "application/json"},
        )
        assert r.status_code == 401
    finally:
        _teardown(client)


def test_malformed_json_after_valid_signature_returns_400():
    """Signature can be valid over arbitrary bytes — but the body must still
    be JSON to be processed. 400 (don't retry), not 401 (don't claim auth
    failure for a body we authenticated)."""
    customer = _customer()
    creds = _creds(remote_site_id="kasa")
    client = _make_client(customer=customer, creds=creds)
    try:
        body = b"not json"
        r = client.post(
            "/api/v1/hooks/stella/kasa",
            content=body,
            headers={"X-Stella-Signature": _sign(SECRET, body), "Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 400
    finally:
        _teardown(client)
