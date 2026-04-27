"""
Idempotency-Key tests (SHARED-CONTRACT.md §6).

The caller (services/order.py) generates `zkr_order_{order_id}` and passes it
to `connector.create_order`. The connector forwards that exact value as the
`Idempotency-Key` header — but only in v1 mode (legacy /api/sync/orders does
not understand it).

Stable derivation means a Zunkiree-side retry of the same logical order
produces the same key; Stella returns the cached response per §6.3.
"""
import httpx
import respx

from app.services.connectors import (
    AgenticomConnector,
    ConnectorOrderDraft,
    ConnectorOrderLineItem,
)


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
async def test_v1_create_order_forwards_caller_idempotency_key():
    route = respx.post("https://example.test/api/sync/v1/orders").mock(
        return_value=httpx.Response(201, json={"order_number": "STELLA-1"}),
    )
    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "sync_key_id": "ssk_live_abc",
            "sync_key_secret": "ssk_sec_def",
            "remote_site_id": "kasa-stella",
        }
    )
    await conn.create_order(_draft(), idempotency_key="zkr_order_internal-pk-42")

    assert route.calls[0].request.headers["Idempotency-Key"] == "zkr_order_internal-pk-42"


@respx.mock
async def test_v1_create_order_retry_with_same_key_produces_same_header():
    """Two calls with the same logical order ID (caller derives the same
    f"zkr_order_{id}" string) produce identical Idempotency-Key headers.
    Verifies the contract that lets Stella cache + return prior response
    on retry without creating a duplicate order."""
    route = respx.post("https://example.test/api/sync/v1/orders").mock(
        return_value=httpx.Response(201, json={"order_number": "STELLA-2"}),
    )
    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "sync_key_id": "ssk_live_abc",
            "sync_key_secret": "ssk_sec_def",
            "remote_site_id": "kasa-stella",
        }
    )
    key = f"zkr_order_{'order-internal-77'}"
    await conn.create_order(_draft(), idempotency_key=key)
    await conn.create_order(_draft(), idempotency_key=key)

    assert route.calls[0].request.headers["Idempotency-Key"] == key
    assert route.calls[1].request.headers["Idempotency-Key"] == key


@respx.mock
async def test_legacy_create_order_omits_idempotency_key():
    """Legacy /api/sync/orders never carries Idempotency-Key — Stella's legacy
    endpoint doesn't implement caching. Same Z2 contract; Z3 doesn't change it."""
    route = respx.post("https://example.test/api/sync/orders").mock(
        return_value=httpx.Response(201, json={"order_number": "STELLA-3"}),
    )
    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "legacy_shared_secret": "shared",
            "remote_site_id": "kasa",
        }
    )
    await conn.create_order(_draft(), idempotency_key="zkr_order_should-be-dropped")

    assert "Idempotency-Key" not in route.calls[0].request.headers
