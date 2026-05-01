"""
Unit tests for `AgenticomConnector.find_product_by_external_id`.

This is the workaround helper used by the cart-storefront-realtime path
(tools.py `_storefront_realtime_add_to_cart`). `connector.get_product`
raises NotImplementedError in legacy mode and Phase-1 tenants are still
on the global secret, so the cart path needs a mode-agnostic lookup.

Validates the broad-search + local filter contract: hit Stella's
`/api/sync/products?search=&limit=N`, then filter the returned list for
the matching `external_id`.
"""
import httpx
import pytest
import respx

from app.services.connectors import AgenticomConnector


def _mk_legacy_connector() -> AgenticomConnector:
    return AgenticomConnector(
        {
            "api_url": "https://example.test",
            "legacy_shared_secret": "shared",
            "remote_site_id": "huba-nepal",
        }
    )


def _product_payload(external_id: str, name: str) -> dict:
    return {
        "id": external_id,
        "name": name,
        "description": "",
        "price": 4500,
        "currency": "NPR",
        "images": [],
        "variants": [],
        "categories": [],
        "tags": [],
        "url": f"https://example.test/p/{name.lower().replace(' ', '-')}",
        "in_stock": True,
        "available": True,
    }


@respx.mock
@pytest.mark.asyncio
async def test_returns_matching_product_when_id_in_catalog():
    """Search returns the catalog; filter picks the row matching external_id."""
    respx.get("https://example.test/api/sync/products").mock(
        return_value=httpx.Response(
            200,
            json={
                "products": [
                    _product_payload("ext-1", "Sherpa Beanie"),
                    _product_payload("ext-2", "Linen Pants"),
                    _product_payload("ext-3", "Mountain Sweater"),
                ]
            },
        )
    )

    conn = _mk_legacy_connector()
    product = await conn.find_product_by_external_id("ext-2")

    assert product is not None
    assert product.external_id == "ext-2"
    assert product.name == "Linen Pants"


@respx.mock
@pytest.mark.asyncio
async def test_returns_none_when_id_not_in_catalog():
    """Search returns the catalog but external_id isn't in it — return None
    rather than raising. Caller maps this to 'Product not found'."""
    respx.get("https://example.test/api/sync/products").mock(
        return_value=httpx.Response(
            200, json={"products": [_product_payload("ext-1", "Sherpa Beanie")]},
        )
    )

    conn = _mk_legacy_connector()
    product = await conn.find_product_by_external_id("ext-missing")

    assert product is None


@respx.mock
@pytest.mark.asyncio
async def test_returns_none_when_external_id_is_empty_no_request():
    """Empty external_id should short-circuit before hitting the network —
    no point burning a search round-trip."""
    route = respx.get("https://example.test/api/sync/products").mock(
        return_value=httpx.Response(200, json={"products": []})
    )

    conn = _mk_legacy_connector()
    product = await conn.find_product_by_external_id("")

    assert product is None
    assert not route.called


@respx.mock
@pytest.mark.asyncio
async def test_uses_empty_query_and_includes_out_of_stock():
    """Wire-level contract: query is the empty string (Stella stage returns
    the full catalog for that input — verified empirically) and
    in_stock_only=False so out-of-stock products still surface for the
    'currently out of stock' branch in tools.py."""
    route = respx.get("https://example.test/api/sync/products").mock(
        return_value=httpx.Response(200, json={"products": []})
    )

    conn = _mk_legacy_connector()
    await conn.find_product_by_external_id("ext-1", catalog_limit=50)

    sent = route.calls[0].request
    params = dict(sent.url.params)
    assert params.get("search") == ""
    assert params.get("limit") == "50"
    # in_stock_only=False -> the 'in_stock' query param must NOT be set
    assert "in_stock" not in params
