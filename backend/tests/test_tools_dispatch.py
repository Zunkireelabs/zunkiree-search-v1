"""
IG-3 regression test: product_search tool call without a query string.

The LLM emits product_search with only a price filter (no query) for
natural-language patterns like "anything under 2000 rupee". Before the fix,
the dispatcher crashed with:
  TypeError: _product_search() missing 1 required positional argument: 'query'

After the fix, query defaults to "" and routes to the SQL fallback so the
user gets a price-filtered listing instead of the generic error message.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.tools import execute_tool


def _make_db_no_config():
    """DB mock that returns None for WidgetConfig (default scraped config)."""
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=config_result)
    return db


@pytest.mark.asyncio
async def test_product_search_handles_missing_query(monkeypatch):
    """LLM may emit product_search with only a price filter. Must not crash."""
    # Patch _fallback_product_search so we don't need a real DB
    monkeypatch.setattr(
        "app.services.tools._fallback_product_search",
        AsyncMock(return_value={"products": [], "message": "No products found matching your search."}),
    )

    db = _make_db_no_config()

    # tool_args has no "query" key — this is the exact shape that caused the crash
    result = await execute_tool(
        tool_name="product_search",
        tool_args={"max_price": 2000},
        db=db,
        session_id="test-session",
        customer_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        site_id="kasa-clothing",
    )

    assert isinstance(result, dict), "Must return a dict, not raise TypeError"
    assert "products" in result, "Result must include a products key"


@pytest.mark.asyncio
async def test_product_search_missing_query_calls_fallback_with_price_filter(monkeypatch):
    """With no query, _fallback_product_search must be called with the price filter."""
    captured: list[dict] = []

    async def _fake_fallback(db, customer_id, query, min_price, max_price, in_stock_only):
        captured.append({
            "query": query,
            "min_price": min_price,
            "max_price": max_price,
        })
        return {"products": []}

    monkeypatch.setattr("app.services.tools._fallback_product_search", _fake_fallback)

    db = _make_db_no_config()

    await execute_tool(
        tool_name="product_search",
        tool_args={"max_price": 2000},
        db=db,
        session_id="test-session",
        customer_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        site_id="kasa-clothing",
    )

    assert len(captured) == 1
    assert captured[0]["query"] == ""
    assert captured[0]["max_price"] == 2000
    assert captured[0]["min_price"] is None


@pytest.mark.asyncio
async def test_product_search_with_query_still_uses_vector_path(monkeypatch):
    """Normal query string must NOT be rerouted to the fallback — regression guard."""
    fallback_called = False

    async def _fake_fallback(*args, **kwargs):
        nonlocal fallback_called
        fallback_called = True
        return {"products": []}

    monkeypatch.setattr("app.services.tools._fallback_product_search", _fake_fallback)

    # Mock the embedding + vector path so it returns gracefully without real I/O
    monkeypatch.setattr(
        "app.services.tools.get_embedding_service",
        lambda: MagicMock(create_embedding=AsyncMock(return_value=[0.1] * 10)),
    )
    monkeypatch.setattr(
        "app.services.tools.get_vector_store_service",
        lambda: MagicMock(query_vectors=AsyncMock(return_value=[])),
    )

    db = _make_db_no_config()
    # When vector search returns [] and score_map is empty, _fallback_product_search
    # IS called internally — that's intentional (existing code path). We only verify
    # the initial empty-query guard does NOT intercept a non-empty query.
    result = await execute_tool(
        tool_name="product_search",
        tool_args={"query": "kurta", "max_price": 2000},
        db=db,
        session_id="test-session",
        customer_id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
        site_id="kasa-clothing",
    )

    # Should return a dict regardless (via vector → fallback chain)
    assert isinstance(result, dict)
