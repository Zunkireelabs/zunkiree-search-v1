"""
Z4 connector additions — get_product (v1 GET /api/sync/v1/products/{id}) and
register_webhook (POST /api/sync/v1/webhooks). Both require v1-mode creds;
legacy-mode invocation must raise NotImplementedError so the dispatcher
fails loudly rather than calling a wrong path.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.services.connectors import AgenticomConnector


def _v1_conn() -> AgenticomConnector:
    return AgenticomConnector(
        {
            "api_url": "https://example.test",
            "sync_key_id": "ssk_live_abc",
            "sync_key_secret": "ssk_sec_def",
            "remote_site_id": "kasa-stella",
        }
    )


def _legacy_conn() -> AgenticomConnector:
    return AgenticomConnector(
        {
            "api_url": "https://example.test",
            "legacy_shared_secret": "shared",
            "remote_site_id": "kasa",
        }
    )


# ---------- get_product ----------

@respx.mock
async def test_get_product_v1_uses_bearer_and_v1_path():
    route = respx.get("https://example.test/api/sync/v1/products/p-42").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "p-42",
                "name": "Tee",
                "description": "Cotton tee",
                "price": 1499,
                "currency": "NPR",
                "images": [{"url": "https://cdn.test/tee.jpg"}],
                "variants": [],
                "categories": ["Apparel"],
                "tags": ["new"],
                "in_stock": True,
            },
        ),
    )
    conn = _v1_conn()
    product = await conn.get_product("p-42")

    sent = route.calls[0].request
    assert sent.url.path == "/api/sync/v1/products/p-42"
    assert sent.headers["Authorization"] == "Bearer ssk_sec_def"
    assert sent.headers["X-Stella-Site-Id"] == "kasa-stella"
    assert "X-Correlation-Id" in sent.headers
    assert product.external_id == "p-42"
    assert product.name == "Tee"


@respx.mock
async def test_get_product_tolerates_envelope_wrapper():
    """Stella may return either bare {id, name, ...} or {"product": {...}};
    connector must handle both."""
    route = respx.get("https://example.test/api/sync/v1/products/p-7").mock(
        return_value=httpx.Response(
            200, json={"product": {"id": "p-7", "name": "Cap", "currency": "NPR"}},
        ),
    )
    conn = _v1_conn()
    product = await conn.get_product("p-7")
    assert product.external_id == "p-7"
    assert product.name == "Cap"
    assert route.calls.call_count == 1


async def test_get_product_legacy_mode_raises():
    """Legacy mode has no documented single-product GET — fail loudly per
    Z4 lock so the dispatcher's per-handler error isolation kicks in."""
    conn = _legacy_conn()
    with pytest.raises(NotImplementedError):
        await conn.get_product("p-1")


# ---------- register_webhook ----------

@respx.mock
async def test_register_webhook_v1_posts_bearer_and_returns_secret():
    expected_response = {
        "id": "whk_01HT4ABCDEF",
        "url": "https://api.zunkireelabs.com/api/v1/hooks/stella/kasa",
        "events": ["product.updated", "product.deleted"],
        "signing_secret": "whsec_TESTONLY_0123456789",
        "created_at": "2026-04-27T00:00:00Z",
        "is_active": True,
    }
    route = respx.post("https://example.test/api/sync/v1/webhooks").mock(
        return_value=httpx.Response(201, json=expected_response),
    )
    conn = _v1_conn()
    result = await conn.register_webhook(
        "https://api.zunkireelabs.com/api/v1/hooks/stella/kasa",
        ["product.updated", "product.deleted"],
    )

    sent = route.calls[0].request
    assert sent.headers["Authorization"] == "Bearer ssk_sec_def"
    assert sent.headers["X-Stella-Site-Id"] == "kasa-stella"
    assert sent.headers["Content-Type"] == "application/json"
    body = sent.read().decode()
    assert "product.updated" in body
    assert "https://api.zunkireelabs.com/api/v1/hooks/stella/kasa" in body
    assert result["id"] == "whk_01HT4ABCDEF"
    assert result["signing_secret"] == "whsec_TESTONLY_0123456789"


@respx.mock
async def test_register_webhook_rejects_response_without_secret():
    """If Stella's response is missing signing_secret we must NOT silently
    succeed — that would persist a useless creds row that can't verify any
    inbound delivery."""
    route = respx.post("https://example.test/api/sync/v1/webhooks").mock(
        return_value=httpx.Response(201, json={"id": "whk_x"}),  # no signing_secret
    )
    conn = _v1_conn()
    with pytest.raises(Exception):
        await conn.register_webhook(
            "https://api.zunkireelabs.com/api/v1/hooks/stella/kasa",
            ["product.updated"],
        )
    assert route.calls.call_count == 1


async def test_register_webhook_legacy_mode_raises():
    conn = _legacy_conn()
    with pytest.raises(NotImplementedError):
        await conn.register_webhook("https://example.test/hook", ["product.updated"])
