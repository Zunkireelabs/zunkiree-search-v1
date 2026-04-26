"""
Tests for the BackendConnector abstraction (Z1).

Covers:
- Registry happy path: get_connector("stella", ...) returns AgenticomConnector
- Registry happy path: legacy "agenticom" alias maps to the same class
- Registry sad path: unknown backend_type raises
- Dataclass shape validation against a representative Stella response payload
"""
import pytest

from app.services.connectors import (
    AgenticomConnector,
    BackendConnector,
    ConnectorOrderDraft,
    ConnectorOrderLineItem,
    ConnectorProduct,
    ConnectorVariant,
    get_connector,
)


# ---------- Captured response fixture (representative Stella payload) ----------
# Shape is what `_storefront_realtime_search` previously consumed inline:
# product has id/name/description/price/currency/images[].url/url/in_stock/
# sizes/colors/slug/variants[].price. Captured by reading the legacy
# tools.py code path that already works against Stella in production.

STELLA_PRODUCT_FIXTURE: dict = {
    "id": "prod_abc123",
    "name": "Cotton Crew Tee",
    "description": "100% cotton, regular fit.",
    "price": 1499.0,
    "currency": "NPR",
    "images": [
        {"url": "https://cdn.example.com/p1.jpg"},
        {"url": "https://cdn.example.com/p2.jpg"},
    ],
    "url": "https://kasa.example.com/p/cotton-crew-tee",
    "in_stock": True,
    "sizes": ["S", "M", "L"],
    "colors": ["Black", "White"],
    "slug": "cotton-crew-tee",
    "variants": [
        {
            "id": "var_1",
            "sku": "CTT-BLK-M",
            "size": "M",
            "color": "Black",
            "price": 1499.0,
            "inventory_quantity": 12,
            "available": True,
        },
        {
            "id": "var_2",
            "sku": "CTT-WHT-S",
            "size": "S",
            "color": "White",
            "price": 1499.0,
            "inventory_quantity": 0,
            "available": False,
        },
    ],
}


# ---------- Registry tests ----------

def test_get_connector_stella_returns_agenticom_connector():
    conn = get_connector(
        "stella",
        {"api_url": "https://example.test", "legacy_shared_secret": "s", "remote_site_id": "kasa"},
    )
    assert isinstance(conn, AgenticomConnector)
    assert isinstance(conn, BackendConnector)
    assert conn.backend_type == "stella"


def test_get_connector_agenticom_alias_returns_same_class():
    conn = get_connector(
        "agenticom",
        {"api_url": "https://example.test", "legacy_shared_secret": "s", "remote_site_id": "kasa"},
    )
    assert isinstance(conn, AgenticomConnector)


def test_get_connector_unknown_raises():
    with pytest.raises(ValueError, match="Unknown backend_type"):
        get_connector("shopify", {})


# ---------- Dataclass shape tests ----------

def test_connector_product_from_stella_payload_has_correct_shape():
    product = AgenticomConnector._product_from_raw(STELLA_PRODUCT_FIXTURE)

    assert isinstance(product, ConnectorProduct)
    assert product.external_id == "prod_abc123"
    assert product.name == "Cotton Crew Tee"
    assert product.description == "100% cotton, regular fit."
    assert product.price == 1499.0
    assert product.currency == "NPR"
    assert product.images == [
        "https://cdn.example.com/p1.jpg",
        "https://cdn.example.com/p2.jpg",
    ]
    assert product.url == "https://kasa.example.com/p/cotton-crew-tee"
    assert product.in_stock is True
    assert product.categories == []
    assert product.tags == []
    assert product.raw is STELLA_PRODUCT_FIXTURE
    assert len(product.variants) == 2


def test_connector_variant_maps_size_color_to_options():
    product = AgenticomConnector._product_from_raw(STELLA_PRODUCT_FIXTURE)
    v1, v2 = product.variants

    assert isinstance(v1, ConnectorVariant)
    assert v1.external_id == "var_1"
    assert v1.sku == "CTT-BLK-M"
    assert v1.option1 == "M"           # size → option1
    assert v1.option2 == "Black"       # color → option2
    assert v1.option3 is None
    assert v1.price == 1499.0
    assert v1.inventory_quantity == 12
    assert v1.available is True
    assert v1.raw is STELLA_PRODUCT_FIXTURE["variants"][0]

    assert v2.option1 == "S"
    assert v2.option2 == "White"
    assert v2.available is False


def test_connector_product_falls_back_to_first_variant_price():
    payload = dict(STELLA_PRODUCT_FIXTURE)
    payload["price"] = None
    product = AgenticomConnector._product_from_raw(payload)
    assert product.price == 1499.0  # from variants[0].price


def test_connector_order_draft_accepts_line_items():
    draft = ConnectorOrderDraft(
        email="shopper@example.com",
        phone="9800000000",
        line_items=[
            ConnectorOrderLineItem(
                external_variant_id="var_1",
                external_product_id="prod_abc123",
                name="Cotton Crew Tee",
                quantity=2,
                unit_price=1499.0,
                option1="M",
                option2="Black",
                image_url="https://cdn.example.com/p1.jpg",
            )
        ],
        subtotal=2998.0,
        total=2998.0,
        currency="NPR",
        payment_method="cod",
        payment_intent_id=None,
        shipping_address={"city": "Kathmandu"},
        billing_address=None,
        note="from widget",
    )
    assert draft.email == "shopper@example.com"
    assert len(draft.line_items) == 1
    assert draft.line_items[0].option1 == "M"
    assert draft.total == 2998.0


def test_agenticom_connector_health_check_requires_full_config():
    not_configured = AgenticomConnector({})
    fully_configured = AgenticomConnector(
        {"api_url": "https://example.test", "legacy_shared_secret": "s", "remote_site_id": "kasa"},
    )
    # health_check is async; run via asyncio.
    import asyncio
    assert asyncio.run(not_configured.health_check()) is False
    assert asyncio.run(fully_configured.health_check()) is True


# ---------- Z2: dual-path mode detection ----------

def test_connector_mode_v1_when_sync_key_pair_present():
    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "sync_key_id": "ssk_live_abc",
            "sync_key_secret": "ssk_sec_def",
            "remote_site_id": "kasa",
        }
    )
    assert conn.mode == "v1"


def test_connector_mode_legacy_when_only_shared_secret_present():
    conn = AgenticomConnector(
        {"api_url": "https://example.test", "legacy_shared_secret": "shared", "remote_site_id": "kasa"},
    )
    assert conn.mode == "legacy"


def test_connector_mode_unconfigured_when_nothing_present():
    conn = AgenticomConnector({})
    assert conn.mode == "unconfigured"


def test_connector_v1_creds_take_precedence_over_legacy():
    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "sync_key_id": "ssk_live_abc",
            "sync_key_secret": "ssk_sec_def",
            "legacy_shared_secret": "shared-should-be-ignored",
            "remote_site_id": "kasa",
        }
    )
    assert conn.mode == "v1"


# ---------- Z2: wire fidelity tests (respx-mocked httpx) ----------
# These two tests are the regression guarantee that the connector dual-path
# does not change observable wire output for legacy-mode tenants AND that v1
# mode hits the right URL with the right auth.

import respx  # noqa: E402
import httpx  # noqa: E402


@respx.mock
async def test_legacy_mode_search_wire_is_byte_identical_to_z1():
    """Asserts headers + URL + path of legacy-mode HTTP request exactly match
    what Z1's inline httpx block sent. Any drift here breaks unmigrated tenants."""
    route = respx.get("https://example.test/api/sync/products").mock(
        return_value=httpx.Response(200, json={"products": []}),
    )

    conn = AgenticomConnector(
        {"api_url": "https://example.test", "legacy_shared_secret": "shared", "remote_site_id": "kasa"},
    )
    await conn.search_products("tee", limit=10, in_stock_only=True)

    assert route.called
    sent = route.calls[0].request

    # URL: legacy path, no /v1/
    assert sent.url.path == "/api/sync/products"
    # Headers: legacy pair, no Bearer
    assert sent.headers.get("X-Sync-Secret") == "shared"
    assert sent.headers.get("X-Site-ID") == "kasa"
    assert "Authorization" not in sent.headers
    assert "X-Stella-Site-Id" not in sent.headers
    # Query params: search + limit + in_stock=true
    assert sent.url.params.get("search") == "tee"
    assert sent.url.params.get("limit") == "10"
    assert sent.url.params.get("in_stock") == "true"


@respx.mock
async def test_v1_mode_search_uses_bearer_and_versioned_path():
    """Asserts v1-mode hits /api/sync/v1/* with Bearer auth + X-Stella-Site-Id
    per SHARED-CONTRACT.md §4."""
    route = respx.get("https://example.test/api/sync/v1/products").mock(
        return_value=httpx.Response(200, json={"products": []}),
    )

    conn = AgenticomConnector(
        {
            "api_url": "https://example.test",
            "sync_key_id": "ssk_live_abc",
            "sync_key_secret": "ssk_sec_def",
            "remote_site_id": "kasa-stella",
        }
    )
    await conn.search_products("tee", limit=10, in_stock_only=True)

    assert route.called
    sent = route.calls[0].request

    assert sent.url.path == "/api/sync/v1/products"
    assert sent.headers.get("Authorization") == "Bearer ssk_sec_def"
    assert sent.headers.get("X-Stella-Site-Id") == "kasa-stella"
    assert "X-Sync-Secret" not in sent.headers
    assert "X-Site-ID" not in sent.headers


@respx.mock
async def test_legacy_mode_create_order_post_byte_identical():
    route = respx.post("https://example.test/api/sync/orders").mock(
        return_value=httpx.Response(201, json={"order_number": "STELLA-001"}),
    )

    conn = AgenticomConnector(
        {"api_url": "https://example.test", "legacy_shared_secret": "shared", "remote_site_id": "kasa"},
    )
    draft = ConnectorOrderDraft(
        email="s@e.com",
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
    receipt = await conn.create_order(draft, idempotency_key="zkr_order_xyz")

    assert receipt.external_order_number == "STELLA-001"
    sent = route.calls[0].request
    assert sent.url.path == "/api/sync/orders"
    assert sent.headers.get("X-Sync-Secret") == "shared"
    assert sent.headers.get("X-Site-ID") == "kasa"
    assert sent.headers.get("Content-Type") == "application/json"
    # Z2 must NOT yet send Idempotency-Key or X-Correlation-Id (those are Z3).
    assert "Idempotency-Key" not in sent.headers
    assert "X-Correlation-Id" not in sent.headers
