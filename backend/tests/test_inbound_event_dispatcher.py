"""
Dispatcher tests — routing, success path, error isolation, batch SQL discipline.

Discipline reminders applied:
- The SKIP LOCKED test does NOT assert two concurrent passes drained disjoint
  rows (we don't run two real transactions in unit). Instead we assert the
  raw SQL the picker uses includes "FOR UPDATE SKIP LOCKED" + "LIMIT 50" +
  the 24-hour received_at retention bound — that's the locked behavior.
- Per-handler error isolation asserts processing_error populated AND
  processed_at IS NULL after a failing handler — matching what the next
  tick's WHERE clause keys on for retry.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import inbound_event_dispatcher as dispatcher_mod
from app.services.inbound_event_dispatcher import (
    BATCH_LIMIT,
    BATCH_PICK_SQL,
    HANDLERS,
    handle_product_change,
    handle_product_deleted,
    process_one_batch,
)


# ---------- Picker SQL discipline (locked behavior, not aspirational) ----------

def test_batch_pick_sql_uses_skip_locked_limit_and_retention():
    """Z4 §1.5 lock: SELECT ... FOR UPDATE SKIP LOCKED. Z4 §3.9 retention: 24h."""
    sql = str(BATCH_PICK_SQL)
    assert "FOR UPDATE SKIP LOCKED" in sql.upper()
    assert f"LIMIT {BATCH_LIMIT}" in sql
    assert "24 hours" in sql
    assert "processed_at IS NULL" in sql


def test_batch_limit_is_50_per_brief():
    assert BATCH_LIMIT == 50


# ---------- HANDLERS routing map ----------

def test_handlers_map_routes_product_events_to_full_handler():
    assert HANDLERS["product.created"] is handle_product_change
    assert HANDLERS["product.updated"] is handle_product_change
    assert HANDLERS["variant.created"] is handle_product_change
    assert HANDLERS["variant.updated"] is handle_product_change
    assert HANDLERS["variant.deleted"] is handle_product_change
    assert HANDLERS["product.deleted"] is handle_product_deleted


def test_handlers_map_inventory_and_order_are_stubs():
    """Stubs (locked Z4 §1.3 hybrid) — not the full handler. We just check
    that the stubs are NOT the full implementation; the stub itself is a
    closure that logs + marks processed via the dispatcher's success path."""
    assert HANDLERS["inventory.changed"] is not handle_product_change
    assert HANDLERS["inventory.low"] is not handle_product_change
    assert HANDLERS["order.status_changed"] is not handle_product_change
    assert HANDLERS["order.payment_status_changed"] is not handle_product_change
    assert HANDLERS["order.fulfillment_status_changed"] is not handle_product_change


def test_handlers_map_excludes_order_created():
    """Skip per Z4 §3.4.3 — Zunkiree creates those itself."""
    assert "order.created" not in HANDLERS


# ---------- Success / error isolation via process_one_batch ----------

def _fake_event(event_type="inventory.changed"):
    e = MagicMock()
    e.id = uuid.uuid4()
    e.customer_id = uuid.uuid4()
    e.event_id = f"evt_{uuid.uuid4()}"
    e.event_type = event_type
    e.payload = {"data": {"id": "p1"}}
    e.processed_at = None
    e.processing_error = None
    return e


class _FakeSession:
    """Just enough of an AsyncSession to drive process_one_batch in tests.

    `begin()` returns a context manager whose __aenter__ is a no-op;
    `execute(sql)` returns a result whose .scalars().all() returns ids;
    `get(InboundWebhookEvent, ev_id)` returns the pre-loaded fake row.
    """

    def __init__(self, events):
        self._events = {e.id: e for e in events}
        self._ids = list(self._events.keys())

    def begin(self):
        sess = self

        class _Ctx:
            async def __aenter__(self):
                return sess

            async def __aexit__(self, *a):
                return False

        return _Ctx()

    async def execute(self, _sql):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all.return_value = list(self._ids)
        result.scalars.return_value = scalars
        return result

    async def get(self, _model, ev_id):
        return self._events.get(ev_id)


@pytest.mark.asyncio
async def test_successful_handler_advances_processed_at_and_clears_error():
    """Stub handler succeeds → processed_at set, processing_error cleared."""
    e = _fake_event(event_type="inventory.changed")
    session = _FakeSession([e])

    count = await process_one_batch(session)  # type: ignore[arg-type]

    assert count == 1
    assert isinstance(e.processed_at, datetime)
    assert e.processing_error is None


@pytest.mark.asyncio
async def test_failing_handler_records_error_and_leaves_processed_at_null():
    """Per Z4 §3.9: on handler exception, processing_error is set and
    processed_at stays NULL so the next tick retries."""
    e = _fake_event(event_type="product.updated")
    session = _FakeSession([e])

    async def boom(_db, _ev):
        raise RuntimeError("Pinecone is down")

    with patch.dict(HANDLERS, {"product.updated": boom}):
        count = await process_one_batch(session)  # type: ignore[arg-type]

    assert count == 0
    assert e.processed_at is None
    assert e.processing_error is not None
    assert "Pinecone is down" in e.processing_error


@pytest.mark.asyncio
async def test_unknown_event_type_marks_processed_with_note():
    """Unknown event types should not block the queue — mark processed with
    a processing_error note and move on."""
    e = _fake_event(event_type="unknown.event.type")
    session = _FakeSession([e])

    count = await process_one_batch(session)  # type: ignore[arg-type]

    assert count == 1
    assert isinstance(e.processed_at, datetime)
    assert e.processing_error is not None
    assert "no handler" in e.processing_error


@pytest.mark.asyncio
async def test_one_failing_handler_does_not_block_others():
    """Per-handler error isolation: a bad event doesn't poison the batch."""
    bad = _fake_event(event_type="product.updated")
    good = _fake_event(event_type="inventory.changed")
    session = _FakeSession([bad, good])

    async def boom(_db, _ev):
        raise RuntimeError("upstream 500")

    with patch.dict(HANDLERS, {"product.updated": boom}):
        count = await process_one_batch(session)  # type: ignore[arg-type]

    assert count == 1  # only the good one advanced
    assert bad.processed_at is None
    assert "upstream 500" in (bad.processing_error or "")
    assert good.processed_at is not None
    assert good.processing_error is None


# ---------- handle_product_change full-impl test ----------

@pytest.mark.asyncio
async def test_handle_product_change_calls_get_product_then_upserts_vector():
    """Full handler must (a) resolve the connector via ConnectorResolver,
    (b) call connector.get_product(external_id), (c) embed the result, (d)
    upsert the vector to Pinecone in the tenant's namespace.
    """
    event = MagicMock()
    event.id = uuid.uuid4()
    event.customer_id = uuid.uuid4()
    event.event_id = "evt_x"
    event.event_type = "product.updated"
    event.payload = {"data": {"id": "stella-product-42"}}

    customer = MagicMock()
    customer.id = event.customer_id
    customer.site_id = "kasa"

    session = AsyncMock()
    session.get = AsyncMock(return_value=customer)

    fake_product = MagicMock()
    fake_product.name = "Tee"
    fake_product.description = "Cotton tee"
    fake_product.categories = ["Apparel"]
    fake_product.tags = ["new"]
    fake_product.price = 1499.0
    fake_product.currency = "NPR"

    fake_connector = MagicMock()
    fake_connector.get_product = AsyncMock(return_value=fake_product)

    fake_resolver = AsyncMock(return_value=fake_connector)

    fake_embed_service = MagicMock()
    fake_embed_service.create_embeddings = AsyncMock(return_value=[[0.1] * 8])
    fake_vector_store = MagicMock()
    fake_vector_store.upsert_vectors = AsyncMock()

    with (
        patch.object(dispatcher_mod.ConnectorResolver, "for_tenant", fake_resolver),
        patch.object(dispatcher_mod, "get_embedding_service", lambda: fake_embed_service),
        patch.object(dispatcher_mod, "get_vector_store_service", lambda: fake_vector_store),
    ):
        await handle_product_change(session, event)

    fake_connector.get_product.assert_awaited_once_with("stella-product-42")
    fake_embed_service.create_embeddings.assert_awaited_once()
    fake_vector_store.upsert_vectors.assert_awaited_once()
    args, kwargs = fake_vector_store.upsert_vectors.call_args
    upserted_vectors = args[0]
    assert upserted_vectors[0]["id"] == "stella_product_stella-product-42"
    assert kwargs.get("namespace") == "kasa"


@pytest.mark.asyncio
async def test_handle_product_deleted_calls_delete_vectors():
    event = MagicMock()
    event.id = uuid.uuid4()
    event.customer_id = uuid.uuid4()
    event.event_id = "evt_del"
    event.event_type = "product.deleted"
    event.payload = {"data": {"id": "stella-product-99"}}

    customer = MagicMock()
    customer.id = event.customer_id
    customer.site_id = "kasa"

    session = AsyncMock()
    session.get = AsyncMock(return_value=customer)

    fake_vector_store = MagicMock()
    fake_vector_store.delete_vectors = AsyncMock()

    with patch.object(dispatcher_mod, "get_vector_store_service", lambda: fake_vector_store):
        await handle_product_deleted(session, event)

    fake_vector_store.delete_vectors.assert_awaited_once_with(
        ["stella_product_stella-product-99"], namespace="kasa",
    )
