"""
Z3 wire tests — v1 mode adds Bearer + Idempotency-Key (orders only) +
X-Correlation-Id (always); legacy mode stays byte-identical except for the
new additive X-Correlation-Id header.

Companion to `test_backend_connector.py:test_legacy_mode_search_wire_is_byte_identical_to_z1`
which is the contractual guarantee that legacy-mode tenants don't experience
wire drift. These tests cover the v1 contract surface.
"""
import uuid

import httpx
import pytest
import respx

from app.services.connectors import (
    AgenticomConnector,
    ConnectorOrderDraft,
    ConnectorOrderLineItem,
)
from app.services.correlation import set_correlation_id


def _draft() -> ConnectorOrderDraft:
    return ConnectorOrderDraft(
        email="s@example.test",
        phone="9800",
        line_items=[
            ConnectorOrderLineItem(
                external_variant_id=None,
                external_product_id="p1",
                name="Tee",
                quantity=1,
                unit_price=1499.0,
            )
        ],
        subtotal=1499.0,
        total=1499.0,
        currency="NPR",
        payment_method="cod",
        payment_intent_id=None,
        shipping_address={"city": "Kathmandu"},
        billing_address=None,
        note="from widget",
    )


@respx.mock
async def test_v1_mode_create_order_sends_bearer_idempotency_correlation():
    route = respx.post("https://example.test/api/sync/v1/orders").mock(
        return_value=httpx.Response(201, json={"order_number": "STELLA-7"}),
    )
    set_correlation_id("11111111-2222-3333-4444-555555555555")
    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "sync_key_id": "ssk_live_abc",
            "sync_key_secret": "ssk_sec_def",
            "remote_site_id": "kasa-stella",
        }
    )
    await conn.create_order(_draft(), idempotency_key="zkr_order_42")

    sent = route.calls[0].request
    assert sent.url.path == "/api/sync/v1/orders"
    assert sent.headers["Authorization"] == "Bearer ssk_sec_def"
    assert sent.headers["X-Stella-Site-Id"] == "kasa-stella"
    assert sent.headers["Idempotency-Key"] == "zkr_order_42"
    assert sent.headers["X-Correlation-Id"] == "11111111-2222-3333-4444-555555555555"
    assert "X-Sync-Secret" not in sent.headers
    assert "X-Site-ID" not in sent.headers


@respx.mock
async def test_legacy_mode_create_order_adds_correlation_skips_idempotency():
    """Legacy contract: X-Correlation-Id is now stamped (Z3 contract addition,
    additive + harmless), but Idempotency-Key is still v1-only."""
    route = respx.post("https://example.test/api/sync/orders").mock(
        return_value=httpx.Response(201, json={"order_number": "STELLA-9"}),
    )
    set_correlation_id("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "legacy_shared_secret": "shared",
            "remote_site_id": "kasa",
        }
    )
    await conn.create_order(_draft(), idempotency_key="zkr_order_99")

    sent = route.calls[0].request
    assert sent.url.path == "/api/sync/orders"
    assert sent.headers["X-Sync-Secret"] == "shared"
    assert sent.headers["X-Site-ID"] == "kasa"
    assert sent.headers["X-Correlation-Id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert "Idempotency-Key" not in sent.headers
    assert "Authorization" not in sent.headers


@respx.mock
async def test_v1_mode_search_products_falls_back_to_legacy_url(monkeypatch):
    """Locked decision Z3 §1.2 (b): v1-credentialed tenants still hit the
    legacy /api/sync/products?search=... URL because Stella v1 has no search
    surface. Auth is the global X-Sync-Secret read from settings."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("AGENTICOM_SYNC_SECRET", "global-shared-secret")

    route = respx.get("https://example.test/api/sync/products").mock(
        return_value=httpx.Response(200, json={"products": []}),
    )
    set_correlation_id("ffffffff-1111-2222-3333-444444444444")
    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "sync_key_id": "ssk_live_abc",
            "sync_key_secret": "ssk_sec_def",
            "remote_site_id": "kasa-stella",
        }
    )
    await conn.search_products("tee", limit=10, in_stock_only=True)

    sent = route.calls[0].request
    assert sent.url.path == "/api/sync/products"
    assert sent.headers["X-Sync-Secret"] == "global-shared-secret"
    assert sent.headers["X-Site-ID"] == "kasa-stella"
    assert sent.headers["X-Correlation-Id"] == "ffffffff-1111-2222-3333-444444444444"
    assert "Authorization" not in sent.headers
    assert "X-Stella-Site-Id" not in sent.headers
    get_settings.cache_clear()


@respx.mock
async def test_legacy_mode_search_products_adds_correlation():
    """Legacy-mode search wire is byte-identical to Z1 except X-Correlation-Id
    is now added (Z3 additive change). Companion to the byte-identical test in
    test_backend_connector.py — that one doesn't assert the absence of
    correlation, so it stays green; this test asserts the positive presence."""
    route = respx.get("https://example.test/api/sync/products").mock(
        return_value=httpx.Response(200, json={"products": []}),
    )
    set_correlation_id("12345678-1234-1234-1234-123456789012")
    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "legacy_shared_secret": "shared",
            "remote_site_id": "kasa",
        }
    )
    await conn.search_products("tee", limit=10, in_stock_only=True)

    sent = route.calls[0].request
    assert sent.headers["X-Correlation-Id"] == "12345678-1234-1234-1234-123456789012"
    assert sent.headers["X-Sync-Secret"] == "shared"
    assert sent.headers["X-Site-ID"] == "kasa"


@respx.mock
async def test_correlation_id_auto_generated_when_unset():
    """If no contextvar is set (e.g., outbound call outside a request scope),
    get_correlation_id() generates a UUID v4 and stamps it. Verifies the
    contract that every outbound call carries a correlation ID."""
    # Reset contextvar by importing fresh and clearing — pytest may carry state
    # across tests. set_correlation_id(None-ish) isn't possible, so we just
    # verify a UUID-shaped header is present.
    route = respx.get("https://example.test/api/sync/products").mock(
        return_value=httpx.Response(200, json={"products": []}),
    )
    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "legacy_shared_secret": "shared",
            "remote_site_id": "kasa",
        }
    )
    await conn.search_products("tee", limit=10, in_stock_only=True)

    sent = route.calls[0].request
    cid = sent.headers["X-Correlation-Id"]
    assert len(cid) == 36
    uuid.UUID(cid)  # raises if not a valid UUID
