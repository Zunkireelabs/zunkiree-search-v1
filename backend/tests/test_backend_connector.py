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
