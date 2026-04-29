"""HMAC fail-closed tests for POST /webhooks/meta (Z-Ops hardening, #16).

Pre-fix the handler logged invalid signatures and continued processing —
anyone with the public webhook URL could forge inbound payloads. These
tests pin the new behavior:

- mismatched X-Hub-Signature-256 → 403 invalid_signature
- missing X-Hub-Signature-256 header → 403 invalid_signature
- empty META_APP_SECRET → 503 service_unavailable
- valid signature → 200 status:ok
"""
from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import chatbot_webhooks as cw_module
from app.api.chatbot_webhooks import router as chatbot_router


SECRET = "test_meta_app_secret_value"


def _sign(secret: str, body: bytes) -> str:
    sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def _client_with_secret(monkeypatch: pytest.MonkeyPatch, secret_value: str) -> TestClient:
    monkeypatch.setattr(cw_module.settings, "meta_app_secret", secret_value)
    app = FastAPI()
    app.include_router(chatbot_router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)


def test_invalid_signature_returns_403_with_envelope(monkeypatch):
    client = _client_with_secret(monkeypatch, SECRET)
    body = b'{"object":"instagram","entry":[]}'
    resp = client.post(
        "/api/v1/webhooks/meta",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "invalid_signature"


def test_missing_signature_header_returns_403(monkeypatch):
    client = _client_with_secret(monkeypatch, SECRET)
    body = b'{"object":"instagram","entry":[]}'
    resp = client.post(
        "/api/v1/webhooks/meta",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "invalid_signature"


def test_empty_app_secret_returns_503_service_unavailable(monkeypatch):
    client = _client_with_secret(monkeypatch, "")
    body = b'{"object":"instagram","entry":[]}'
    resp = client.post(
        "/api/v1/webhooks/meta",
        content=body,
        headers={"X-Hub-Signature-256": _sign("any", body), "Content-Type": "application/json"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "service_unavailable"


def test_valid_signature_processes_normally(monkeypatch):
    client = _client_with_secret(monkeypatch, SECRET)
    # Empty entries list so the dispatcher loop has nothing to do — we are only
    # verifying that signature verification passes through to the handler body.
    body = b'{"object":"instagram","entry":[]}'
    resp = client.post(
        "/api/v1/webhooks/meta",
        content=body,
        headers={"X-Hub-Signature-256": _sign(SECRET, body), "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
