"""
Cart storefront/realtime awareness — `_add_to_cart` must route to the
connector for tenants whose products live in an external backend (Stella),
because their local `Product` table is empty by design.

Mirrors the mock-at-boundary pattern from test_z5_order_external_ids.py:
patch `ConnectorResolver.for_tenant` to return an `AsyncMock`-shaped
connector, exercise `_add_to_cart` directly, and assert the right path
was taken.
"""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.connectors.agenticom_connector import (
    AgenticomConnector,
    ConnectorRequestError,
)
from app.services.connectors.base import ConnectorProduct
from app.services.tools import _add_to_cart


def _connector_product(
    *,
    external_id: str = "stella-prod-1",
    name: str = "Linen Pants",
    price: float = 4500.0,
    in_stock: bool = True,
) -> ConnectorProduct:
    return ConnectorProduct(
        external_id=external_id,
        name=name,
        description="Lightweight linen trousers",
        price=price,
        currency="NPR",
        images=["https://example.test/img.jpg"],
        variants=[],
        categories=[],
        tags=[],
        url="https://example.test/p/linen-pants",
        in_stock=in_stock,
        raw={},
    )


def _patch_resolver(monkeypatch, connector):
    from app.services.connectors import resolver as resolver_module

    async def _fake_for_tenant(db, customer_id, backend_type="stella"):
        return connector

    monkeypatch.setattr(
        resolver_module.ConnectorResolver, "for_tenant", staticmethod(_fake_for_tenant)
    )


def _settings_configured(monkeypatch):
    from app.config import get_settings
    s = get_settings()
    monkeypatch.setattr(s, "agenticom_api_url", "https://example.test", raising=False)
    monkeypatch.setattr(s, "agenticom_sync_secret", "legacy-shared", raising=False)


def _stub_widget_config(*, product_source: str, fetch_mode: str = "realtime"):
    """Build a fake WidgetConfig row that the dispatcher's branching reads."""
    cfg = MagicMock()
    cfg.product_source = product_source
    cfg.storefront_fetch_mode = fetch_mode
    return cfg


def _stub_local_product(*, name: str = "Local Tee", in_stock: bool = True) -> MagicMock:
    p = MagicMock()
    p.name = name
    p.price = 1200.0
    p.currency = "NPR"
    p.images = json.dumps([])
    p.url = ""
    p.in_stock = in_stock
    return p


def _make_async_db(*results):
    """Build an AsyncMock DB whose execute() returns the supplied result objects
    in order. `db.add` is overridden to a sync MagicMock since SQLAlchemy's add
    is synchronous — leaving it as AsyncMock raises 'coroutine never awaited'."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=list(results))
    db.add = MagicMock()
    return db


def _result_with(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _make_db_with_widget_config(config):
    """Storefront/realtime path: one SELECT for WidgetConfig, then save_to_db's
    SELECT for ShoppingCart returns None so the service inserts a new row."""
    return _make_async_db(_result_with(config), _result_with(None))


def _make_db_for_legacy_path(*, config, local_product):
    """Legacy path needs three execute() returns: WidgetConfig, Product, Cart."""
    return _make_async_db(
        _result_with(config),
        _result_with(local_product),
        _result_with(None),
    )


def _reset_cart_singleton():
    """Cart service holds module-level state; reset between tests."""
    from app.services import cart as cart_module
    cart_module._cart_service = None


@pytest.fixture(autouse=True)
def _isolate_cart():
    _reset_cart_singleton()
    yield
    _reset_cart_singleton()


@pytest.mark.asyncio
async def test_storefront_realtime_routes_to_connector_and_populates_cart(monkeypatch):
    """When product_source='storefront' + fetch_mode='realtime', the function
    must call connector.find_product_by_external_id (NOT the local Product
    table) and use the returned data to populate the cart."""
    _settings_configured(monkeypatch)

    connector = MagicMock()
    connector.find_product_by_external_id = AsyncMock(
        return_value=_connector_product(external_id="stella-pants-42")
    )
    _patch_resolver(monkeypatch, connector)

    db = _make_db_with_widget_config(
        _stub_widget_config(product_source="storefront", fetch_mode="realtime")
    )

    result = await _add_to_cart(
        db=db,
        session_id="sess-realtime-1",
        customer_id=uuid.uuid4(),
        product_id="stella-pants-42",  # opaque string — UUID parse must NOT run
        quantity=2,
        size="M",
    )

    connector.find_product_by_external_id.assert_awaited_once_with("stella-pants-42")
    assert "error" not in result
    assert result["message"] == "Added Linen Pants to your cart!"
    cart_items = result["cart"]["items"]
    assert len(cart_items) == 1
    assert cart_items[0]["product_id"] == "stella-pants-42"
    assert cart_items[0]["name"] == "Linen Pants"
    assert cart_items[0]["price"] == 4500.0
    assert cart_items[0]["quantity"] == 2
    assert cart_items[0]["size"] == "M"


@pytest.mark.asyncio
async def test_legacy_scraped_mode_unchanged_regression_guard(monkeypatch):
    """Scraped tenants (default) must keep using the local Product table —
    the new branching is additive only. This is the regression guard the
    brief calls out: every test that exercised the legacy path before must
    still pass."""
    _settings_configured(monkeypatch)

    connector = MagicMock()
    connector.find_product_by_external_id = AsyncMock(
        return_value=_connector_product()  # would succeed if accidentally called
    )
    _patch_resolver(monkeypatch, connector)

    pid = uuid.uuid4()
    db = _make_db_for_legacy_path(
        config=_stub_widget_config(product_source="scraped", fetch_mode="synced"),
        local_product=_stub_local_product(name="Local Tee"),
    )

    result = await _add_to_cart(
        db=db,
        session_id="sess-legacy-1",
        customer_id=uuid.uuid4(),
        product_id=str(pid),  # legacy path REQUIRES UUID-shaped string
        quantity=1,
    )

    # Connector must NOT have been called — legacy path takes the local DB lookup.
    connector.find_product_by_external_id.assert_not_awaited()
    assert "error" not in result
    assert result["message"] == "Added Local Tee to your cart!"


@pytest.mark.asyncio
async def test_storefront_realtime_connector_error_returns_graceful_message(monkeypatch):
    """When the connector raises ConnectorRequestError (Stella down, auth
    failure, etc.), the function must return a clean error dict — no
    exception propagation up to the caller (the agent's tool runner can't
    handle exceptions)."""
    _settings_configured(monkeypatch)

    connector = MagicMock()
    connector.find_product_by_external_id = AsyncMock(
        side_effect=ConnectorRequestError(502, "Bad Gateway")
    )
    _patch_resolver(monkeypatch, connector)

    db = _make_db_with_widget_config(
        _stub_widget_config(product_source="storefront", fetch_mode="realtime")
    )

    result = await _add_to_cart(
        db=db,
        session_id="sess-realtime-err",
        customer_id=uuid.uuid4(),
        product_id="stella-prod-x",
    )

    assert result == {"error": "Could not reach storefront."}


@pytest.mark.asyncio
async def test_storefront_realtime_coerces_string_price_from_connector(monkeypatch):
    """Stella's legacy /api/sync/products returns price as a JSON string
    ("3200.00"), but ConnectorProduct.price is typed Optional[float] and the
    cart path does arithmetic on it (subtotal calc). The contract is honored
    by source-side coercion in `AgenticomConnector._product_from_raw`; this
    test exercises that source → cart integration end-to-end by feeding a
    raw Stella-shaped dict through the decoder before handing the result to
    `_add_to_cart`. If the source coercion regresses, this test catches it
    via TypeError in `_recalculate` ('int' + 'str')."""
    _settings_configured(monkeypatch)

    # Raw Stella payload shape — what the wire actually returns — with the
    # offending string price. Routing this through `_product_from_raw`
    # mirrors the production path and gives the test the correct boundary.
    raw = {
        "id": "stella-prod-strprice",
        "name": "Linen Pants",
        "description": "Lightweight linen trousers",
        "price": "3200.00",
        "currency": "NPR",
        "images": [{"url": "https://example.test/img.jpg"}],
        "url": "https://example.test/p/linen-pants",
        "in_stock": True,
        "variants": [],
    }
    decoded = AgenticomConnector._product_from_raw(raw)
    assert isinstance(decoded.price, float)  # sanity: source coerced before cart

    connector = MagicMock()
    connector.find_product_by_external_id = AsyncMock(return_value=decoded)
    _patch_resolver(monkeypatch, connector)

    db = _make_db_with_widget_config(
        _stub_widget_config(product_source="storefront", fetch_mode="realtime")
    )

    result = await _add_to_cart(
        db=db,
        session_id="sess-realtime-strprice",
        customer_id=uuid.uuid4(),
        product_id="stella-prod-strprice",
    )

    assert "error" not in result
    assert result["cart"]["items"][0]["price"] == 3200.0
    assert result["cart"]["subtotal"] == 3200.0


@pytest.mark.asyncio
async def test_storefront_realtime_missing_product_returns_not_found(monkeypatch):
    """Connector resolves cleanly but no product matches the external_id —
    return the same 'Product not found' message the legacy path uses, so
    downstream LLM phrasing stays consistent."""
    _settings_configured(monkeypatch)

    connector = MagicMock()
    connector.find_product_by_external_id = AsyncMock(return_value=None)
    _patch_resolver(monkeypatch, connector)

    db = _make_db_with_widget_config(
        _stub_widget_config(product_source="storefront", fetch_mode="realtime")
    )

    result = await _add_to_cart(
        db=db,
        session_id="sess-realtime-404",
        customer_id=uuid.uuid4(),
        product_id="stella-prod-does-not-exist",
    )

    assert result == {"error": "Product not found"}
