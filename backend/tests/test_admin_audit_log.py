"""Tests for the admin_audit_log helper + integration with destructive
admin handlers (Z-Ops hardening, #17).

Two layers:
1. Unit — `log_admin_action` writes a row and is fail-open on errors.
2. Integration — each of the five destructive handlers invokes
   `log_admin_action` with the locked actor / action / payload shape.
   Handler-level integration tests patch `log_admin_action` at the call
   site (NOT the helper module) so handler imports already resolved at
   module-load time still see the patched function.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, Request

from app.services.admin_audit import (
    _extract_ip,
    _resolve_actor_for_admin_tenant,
    log_admin_action,
)


# ---------------------------------------------------------------------------
# Unit: log_admin_action


@pytest.mark.asyncio
async def test_log_admin_action_inserts_row():
    db = AsyncMock()
    captured = {}

    def _capture(row):
        captured["row"] = row

    db.add = MagicMock(side_effect=_capture)

    await log_admin_action(
        db,
        actor="legacy_admin",
        action="customer.deleted",
        target_table="customers",
        target_id=uuid.uuid4(),
        target_site_id="kasa",
        payload={"site_id": "kasa", "name": "Kasa"},
        request=None,
    )

    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    row = captured["row"]
    assert row.actor == "legacy_admin"
    assert row.action == "customer.deleted"
    assert row.target_table == "customers"
    assert row.target_site_id == "kasa"
    assert row.payload_json == {"site_id": "kasa", "name": "Kasa"}
    # request_id is auto-populated from the correlation contextvar.
    assert isinstance(row.request_id, str) and len(row.request_id) > 0


@pytest.mark.asyncio
async def test_log_admin_action_handles_db_error_gracefully():
    """Helper must NOT re-raise — primary destructive op already committed."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock(side_effect=RuntimeError("boom"))
    db.rollback = AsyncMock()

    # Must not raise.
    await log_admin_action(
        db,
        actor="legacy_admin",
        action="customer.deleted",
        target_table="customers",
        target_site_id="kasa",
        payload={},
    )
    db.rollback.assert_awaited_once()


def test_extract_ip_prefers_x_forwarded_for():
    req = MagicMock(spec=Request)
    req.headers = {"x-forwarded-for": "203.0.113.7, 10.0.0.1"}
    req.client = MagicMock(host="127.0.0.1")
    assert _extract_ip(req) == "203.0.113.7"


def test_extract_ip_falls_back_to_client_host():
    req = MagicMock(spec=Request)
    req.headers = {}
    req.client = MagicMock(host="198.51.100.4")
    assert _extract_ip(req) == "198.51.100.4"


def test_extract_ip_returns_none_without_request():
    assert _extract_ip(None) is None


def test_resolve_actor_for_admin_tenant_uses_request_state_token_id():
    req = MagicMock(spec=Request)
    state = MagicMock()
    state.admin_token_id = "zka_live_abcdef"
    req.state = state
    assert _resolve_actor_for_admin_tenant(req) == "tenant_admin:zka_live_abcdef"


def test_resolve_actor_for_admin_tenant_without_token_falls_back():
    req = MagicMock(spec=Request)
    req.state = MagicMock(spec=[])  # no admin_token_id attribute
    assert _resolve_actor_for_admin_tenant(req) == "tenant_admin"


# ---------------------------------------------------------------------------
# Integration: destructive handlers wire log_admin_action with the locked
# actor / action / payload shapes.


def _fake_request() -> Request:
    """Minimal Request stand-in for handler-direct calls. Real wire path
    populates request.state via middleware; here we just provide what the
    handlers / helper actually read."""
    req = MagicMock(spec=Request)
    req.headers = {}
    req.client = MagicMock(host="127.0.0.1")
    state = MagicMock()
    state.admin_token_id = None
    req.state = state
    return req


@pytest.mark.asyncio
async def test_customer_delete_creates_audit_log_row(monkeypatch):
    from app.api import admin as admin_module

    audit_calls = []

    async def fake_audit(db, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(admin_module, "log_admin_action", fake_audit)

    fake_vss = MagicMock()
    fake_vss.delete_namespace = AsyncMock()
    monkeypatch.setattr(admin_module, "get_vector_store_service", lambda: fake_vss)

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"
    customer.name = "Kasa"
    customer.is_active = True
    customer.website_type = "ecommerce"

    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    db = AsyncMock()
    db.execute.side_effect = [customer_result, MagicMock()]  # SELECT, DELETE

    await admin_module.delete_customer(
        site_id="kasa",
        request=_fake_request(),
        confirm=True,
        db=db,
        _="ok",
    )

    fake_vss.delete_namespace.assert_awaited_once_with("kasa")

    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["actor"] == "legacy_admin"
    assert call["action"] == "customer.deleted"
    assert call["target_table"] == "customers"
    assert call["target_site_id"] == "kasa"
    assert call["payload"]["site_id"] == "kasa"
    assert call["payload"]["name"] == "Kasa"
    assert call["payload"]["pinecone_cleanup"] == "ok"


@pytest.mark.asyncio
async def test_customer_delete_audit_records_pinecone_failure(monkeypatch):
    from app.api import admin as admin_module

    audit_calls = []

    async def fake_audit(db, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(admin_module, "log_admin_action", fake_audit)

    fake_vss = MagicMock()
    fake_vss.delete_namespace = AsyncMock(side_effect=RuntimeError("pinecone down"))
    monkeypatch.setattr(admin_module, "get_vector_store_service", lambda: fake_vss)

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"
    customer.name = "Kasa"
    customer.is_active = True
    customer.website_type = None

    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    db = AsyncMock()
    db.execute.side_effect = [customer_result, MagicMock()]

    await admin_module.delete_customer(
        site_id="kasa",
        request=_fake_request(),
        confirm=True,
        db=db,
        _="ok",
    )

    # DB delete still committed despite Pinecone failure.
    db.commit.assert_awaited()
    assert audit_calls[0]["payload"]["pinecone_cleanup"].startswith("failed:")


@pytest.mark.asyncio
async def test_customer_api_key_rotate_creates_audit_log_row(monkeypatch):
    from app.api import admin as admin_module

    audit_calls = []

    async def fake_audit(db, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(admin_module, "log_admin_action", fake_audit)

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    db = AsyncMock()
    db.execute.return_value = customer_result

    resp = await admin_module.rotate_customer_api_key(
        site_id="kasa",
        request=_fake_request(),
        db=db,
        _="ok",
    )

    assert "api_key" in resp
    full_key = resp["api_key"]
    assert full_key.startswith("zk_live_kasa_")

    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["actor"] == "legacy_admin"
    assert call["action"] == "customer_api_key.rotated"
    assert call["target_site_id"] == "kasa"
    # Never log the full secret. Prefix only.
    assert call["payload"]["new_key_prefix"] == full_key[:18]
    assert full_key not in str(call["payload"])


@pytest.mark.asyncio
async def test_tenant_delete_creates_audit_log_row(monkeypatch):
    from app.api import admin_tenants as tenants_module

    audit_calls = []

    async def fake_audit(db, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(tenants_module, "log_admin_action", fake_audit)

    fake_vss = MagicMock()
    fake_vss.delete_namespace = AsyncMock()
    monkeypatch.setattr(tenants_module, "get_vector_store_service", lambda: fake_vss)

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"
    customer.name = "Kasa"
    customer.stella_merchant_id = "mrch_kasa"
    customer.is_active = True
    customer.website_type = "ecommerce"

    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    db = AsyncMock()
    db.execute.side_effect = [customer_result, MagicMock()]

    await tenants_module.delete_tenant(
        site_id="kasa",
        request=_fake_request(),
        confirm=True,
        db=db,
    )

    fake_vss.delete_namespace.assert_awaited_once_with("kasa")
    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["actor"] == "master_admin"
    assert call["action"] == "tenant.deleted"
    assert call["target_table"] == "customers"
    assert call["target_site_id"] == "kasa"
    assert call["payload"]["stella_merchant_id"] == "mrch_kasa"
    assert call["payload"]["pinecone_cleanup"] == "ok"


@pytest.mark.asyncio
async def test_admin_token_rotate_creates_audit_log_row(monkeypatch):
    from app.api import admin_tenants as tenants_module
    from app.services.tenant_provisioning import RotateResult

    audit_calls = []

    async def fake_audit(db, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(tenants_module, "log_admin_action", fake_audit)

    new_id = "zka_live_new1234567890"
    revoked = ["zka_live_old0987654321"]

    async def fake_rotate(self, db, customer_id):
        return RotateResult(
            new_token_id=new_id,
            new_token_secret="zka_sec_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            revoked_token_ids=revoked,
        )

    monkeypatch.setattr(
        tenants_module.TenantProvisioningService, "rotate_admin_token", fake_rotate
    )

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"

    request = _fake_request()
    request.state.admin_token_id = "zka_live_caller00000000"

    db = AsyncMock()

    await tenants_module.rotate_admin_token(
        site_id="kasa",
        request=request,
        customer=customer,
        db=db,
    )

    assert len(audit_calls) == 1
    call = audit_calls[0]
    # actor reflects the caller token, derived from request.state.admin_token_id
    assert call["actor"] == "tenant_admin:zka_live_caller00000000"
    assert call["action"] == "admin_token.rotated"
    assert call["target_table"] == "tenant_admin_tokens"
    assert call["payload"]["new_token_id"] == new_id
    assert call["payload"]["revoked_token_ids"] == revoked


@pytest.mark.asyncio
async def test_chatbot_channel_disconnect_creates_audit_log_row(monkeypatch):
    from app.api import chatbot_admin as ca_module

    audit_calls = []

    async def fake_audit(db, **kwargs):
        audit_calls.append(kwargs)

    monkeypatch.setattr(ca_module, "log_admin_action", fake_audit)

    channel = MagicMock()
    channel.id = uuid.uuid4()
    channel.customer_id = uuid.uuid4()
    channel.platform = "instagram"
    channel.platform_page_id = "17841400000000"
    channel.is_active = True

    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel
    site_result = MagicMock()
    site_result.scalar_one_or_none.return_value = "kasa"

    db = AsyncMock()
    db.execute.side_effect = [channel_result, site_result]

    resp = await ca_module.disconnect_channel(
        channel_id=str(channel.id),
        request=_fake_request(),
        db=db,
    )
    assert resp["status"] == "disconnected"
    # Soft delete: the channel row stays, just is_active flips.
    assert channel.is_active is False

    assert len(audit_calls) == 1
    call = audit_calls[0]
    assert call["actor"] == "legacy_admin"
    assert call["action"] == "chatbot_channel.disconnected"
    assert call["target_table"] == "chatbot_channels"
    assert call["target_site_id"] == "kasa"
    assert call["payload"]["soft_delete"] is True
    assert call["payload"]["platform"] == "instagram"


@pytest.mark.asyncio
async def test_get_admin_tenant_stashes_admin_token_id_on_request_state(monkeypatch):
    """deps.py wiring: matched.token_id is stashed so audit-log callers can
    attribute the action to the specific token used (Z-Ops hardening)."""
    from unittest.mock import patch

    from app.api import deps

    customer_id = uuid.uuid4()
    customer = MagicMock()
    customer.id = customer_id
    customer.site_id = "kasa"

    matched_row = MagicMock()
    matched_row.id = uuid.uuid4()
    matched_row.customer_id = customer_id
    matched_row.token_id = "zka_live_audit99999"
    matched_row.secret_hash = "$argon2id$..."

    candidates_result = MagicMock()
    candidates_result.scalars.return_value.all.return_value = [matched_row]
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer

    db = AsyncMock()
    db.execute.side_effect = [candidates_result, customer_result, MagicMock()]

    request = MagicMock(spec=Request)
    state = MagicMock(spec=[])
    request.state = state

    with patch("app.api.deps.verify_token", return_value=True):
        returned = await deps.get_admin_tenant(
            authorization="Bearer zka_sec_some_padded_value_with_realistic_length_xxxxxx",
            x_zunkiree_site_id="kasa",
            db=db,
            request=request,
        )
    assert returned is customer
    assert request.state.admin_token_id == "zka_live_audit99999"
