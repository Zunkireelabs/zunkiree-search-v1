"""Pinecone cleanup wiring tests for customer DELETE (Z-Ops hardening, #18).

Pre-fix the Postgres row + FK CASCADE removed the merchant from the relational
DB but Pinecone vectors were orphaned. These tests pin that both the legacy
admin DELETE and the Z6 tenant DELETE call delete_namespace(site_id) and
that DB delete still commits when Pinecone fails.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request


def _fake_request() -> Request:
    req = MagicMock(spec=Request)
    req.headers = {}
    req.client = MagicMock(host="127.0.0.1")
    state = MagicMock()
    state.admin_token_id = None
    req.state = state
    return req


def _patch_audit_noop(monkeypatch, module):
    async def _noop(db, **kwargs):
        return None

    monkeypatch.setattr(module, "log_admin_action", _noop)


@pytest.mark.asyncio
async def test_legacy_customer_delete_calls_pinecone_namespace_delete(monkeypatch):
    from app.api import admin as admin_module

    _patch_audit_noop(monkeypatch, admin_module)

    fake_vss = MagicMock()
    fake_vss.delete_namespace = AsyncMock()
    monkeypatch.setattr(admin_module, "get_vector_store_service", lambda: fake_vss)

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa-clothing"
    customer.name = "Kasa"
    customer.is_active = True
    customer.website_type = "ecommerce"

    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    db = AsyncMock()
    db.execute.side_effect = [customer_result, MagicMock()]

    await admin_module.delete_customer(
        site_id="kasa-clothing",
        request=_fake_request(),
        confirm=True,
        db=db,
        _="ok",
    )

    fake_vss.delete_namespace.assert_awaited_once_with("kasa-clothing")
    db.commit.assert_awaited()  # DB delete committed


@pytest.mark.asyncio
async def test_legacy_customer_delete_succeeds_even_if_pinecone_fails(monkeypatch):
    from app.api import admin as admin_module

    _patch_audit_noop(monkeypatch, admin_module)

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

    # Must not raise.
    resp = await admin_module.delete_customer(
        site_id="kasa",
        request=_fake_request(),
        confirm=True,
        db=db,
        _="ok",
    )
    assert "deleted successfully" in resp["message"]
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_z6_tenant_delete_calls_pinecone_namespace_delete(monkeypatch):
    from app.api import admin_tenants as tenants_module

    _patch_audit_noop(monkeypatch, tenants_module)

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
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_z6_tenant_delete_succeeds_even_if_pinecone_fails(monkeypatch):
    from app.api import admin_tenants as tenants_module

    _patch_audit_noop(monkeypatch, tenants_module)

    fake_vss = MagicMock()
    fake_vss.delete_namespace = AsyncMock(side_effect=RuntimeError("pinecone down"))
    monkeypatch.setattr(tenants_module, "get_vector_store_service", lambda: fake_vss)

    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = "kasa"
    customer.name = "Kasa"
    customer.stella_merchant_id = None
    customer.is_active = True
    customer.website_type = None

    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    db = AsyncMock()
    db.execute.side_effect = [customer_result, MagicMock()]

    # Must not raise. delete_tenant returns None (status 204).
    await tenants_module.delete_tenant(
        site_id="kasa",
        request=_fake_request(),
        confirm=True,
        db=db,
    )
    db.commit.assert_awaited()
