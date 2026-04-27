"""
Inbound webhook event dispatcher (Z4 §3.4.3).

Background asyncio task started in `app.main.lifespan`. Every tick:

1. SELECT a small batch (LIMIT 50) of unprocessed events from
   `inbound_webhook_events` ordered by `received_at`, with `FOR UPDATE
   SKIP LOCKED` so that stage and prod containers (or two replicas of the
   same env) never process the same row twice. The 24-hour `received_at`
   bound on the WHERE clause is the natural retry/dead-letter ceiling — old
   stuck rows fall out of the dispatcher's view and are visible to humans
   via direct table query.
2. For each row, route by `event_type` to a handler in HANDLERS.
3. On success, set `processed_at`. On exception, set `processing_error`
   and leave `processed_at` NULL (next tick retries — bounded by 24h).
4. Commit once per batch, releasing the row locks.

Locked decisions (Z4 §1.3 hybrid):
- handle_product_change + handle_product_deleted: full implementation —
  re-fetch from connector, re-embed via existing embeddings/vector_store
  services, upsert/delete from Pinecone in the tenant's namespace.
- handle_inventory_changed / handle_inventory_low / handle_order_*: stubs.
  They log + mark processed. Z5+ fills in real side effects. Stubbing here
  exercises the dispatch + dedupe paths in production from day one without
  taking a database write surface area we don't yet need.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models import Customer, InboundWebhookEvent
from app.services.connectors.resolver import ConnectorResolver
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service

logger = logging.getLogger("zunkiree.inbound_dispatcher")

TICK_INTERVAL_SECONDS = 5
BATCH_LIMIT = 50
RETENTION_INTERVAL = "24 hours"


# Pinecone vector id namespace for Stella-sourced products. Distinct from the
# `product_<uuid>` ids used by the local-scrape ingestion path so the two
# populations never collide.
def _stella_vector_id(external_id: str) -> str:
    return f"stella_product_{external_id}"


def _stella_product_embedding_text(p: Any) -> str:
    """Compose the embedding string for a Stella-sourced product.

    Mirrors the shape used by the local Product.embedding_text() pattern but
    operates on the connector's ConnectorProduct dataclass so the same handler
    works for every BackendConnector implementation that returns one.
    """
    parts: list[str] = []
    if getattr(p, "name", None):
        parts.append(str(p.name))
    if getattr(p, "description", None):
        parts.append(str(p.description))
    if getattr(p, "categories", None):
        parts.append("Categories: " + ", ".join(p.categories))
    if getattr(p, "tags", None):
        parts.append("Tags: " + ", ".join(p.tags))
    if getattr(p, "price", None) is not None:
        currency = getattr(p, "currency", "") or ""
        parts.append(f"Price: {p.price} {currency}".strip())
    return "\n".join(parts).strip() or (getattr(p, "name", None) or "")


# ---------- Concrete handlers ----------

async def handle_product_change(db: AsyncSession, event: InboundWebhookEvent) -> None:
    """Re-fetch the product via the v1 connector and (re-)upsert its embedding.

    Triggered for product.created / product.updated and the variant.* events
    (variant changes reindex the parent product). The `payload.data` contains
    the full product per SHARED-CONTRACT §7.2, but we re-fetch via the
    connector so we converge on Stella's current state if the delivery is
    delayed (retry backoff goes up to 24h per §7.6).
    """
    payload = event.payload or {}
    data = payload.get("data") or {}
    # Variants carry product_id; products carry id.
    external_id = (
        data.get("product_id")
        or data.get("id")
        or (payload.get("data") or {}).get("product", {}).get("id")
    )
    if not external_id:
        raise ValueError(f"event {event.event_id} payload has no product id to resolve")

    customer = await db.get(Customer, event.customer_id)
    if not customer:
        raise ValueError(f"customer {event.customer_id} not found")

    connector = await ConnectorResolver.for_tenant(db, customer.id, "stella")
    product = await connector.get_product(str(external_id))

    embedding_text = _stella_product_embedding_text(product)
    if not embedding_text:
        # Empty product (no name/desc) — skip embed; mark processed so we
        # don't retry forever. Better than crashing the dispatcher.
        logger.info(
            "[INBOUND-DISPATCH] empty product body for %s; skipping embed",
            external_id,
        )
        return

    embeddings = await get_embedding_service().create_embeddings([embedding_text])
    if not embeddings:
        raise RuntimeError(f"embedding service returned no vectors for product {external_id}")

    await get_vector_store_service().upsert_vectors(
        [
            {
                "id": _stella_vector_id(str(external_id)),
                "values": embeddings[0],
                "metadata": {
                    "type": "product",
                    "source": "stella",
                    "external_id": str(external_id),
                    "site_id": customer.site_id,
                    "name": product.name or "",
                },
            }
        ],
        namespace=customer.site_id,
    )


async def handle_product_deleted(db: AsyncSession, event: InboundWebhookEvent) -> None:
    """Drop the Stella-sourced vector from Pinecone. Local Product table is
    not touched — Z4 doesn't add an external_id column to products (locked
    schema scope) and the local-scrape population doesn't share ids with
    Stella's id space."""
    data = (event.payload or {}).get("data") or {}
    external_id = data.get("id")
    if not external_id:
        raise ValueError(f"event {event.event_id} payload has no product id to delete")

    customer = await db.get(Customer, event.customer_id)
    if not customer:
        raise ValueError(f"customer {event.customer_id} not found")

    await get_vector_store_service().delete_vectors(
        [_stella_vector_id(str(external_id))],
        namespace=customer.site_id,
    )


async def _stub_handler(db: AsyncSession, event: InboundWebhookEvent) -> None:
    """Z4 stub for inventory + order events. Logs at INFO and marks processed
    via the dispatcher loop's normal success path. Real side effects land in
    Z5+ when the order/inventory flows are rewritten."""
    logger.info(
        "[INBOUND-DISPATCH] stub-processed event_type=%s event_id=%s customer=%s",
        event.event_type,
        event.event_id,
        event.customer_id,
    )


HANDLERS = {
    "product.created": handle_product_change,
    "product.updated": handle_product_change,
    "product.deleted": handle_product_deleted,
    "variant.created": handle_product_change,
    "variant.updated": handle_product_change,
    "variant.deleted": handle_product_change,
    "inventory.changed": _stub_handler,
    "inventory.low": _stub_handler,
    "order.status_changed": _stub_handler,
    "order.payment_status_changed": _stub_handler,
    "order.fulfillment_status_changed": _stub_handler,
    # Skip order.created — Zunkiree-side originated; we already know.
}


# ---------- Batch picker + tick loop ----------

# Postgres-side serialization between dispatcher replicas. The 24h received_at
# bound is also the natural dead-letter line: rows older than that fall out of
# the dispatcher's view and become visible only via direct query (operators
# can decide whether to manually retry, drop, or keep for forensics).
BATCH_PICK_SQL = text(
    f"""
    SELECT id
    FROM inbound_webhook_events
    WHERE processed_at IS NULL
      AND received_at > NOW() - INTERVAL '{RETENTION_INTERVAL}'
    ORDER BY received_at ASC
    LIMIT {BATCH_LIMIT}
    FOR UPDATE SKIP LOCKED
    """
)


async def process_one_batch(session: AsyncSession) -> int:
    """Pick + process one batch under one transaction. Returns the number of
    rows whose processed_at was advanced.

    Public for the tests in test_inbound_event_dispatcher — calling this
    directly bypasses the asyncio-loop scheduler so tests can assert exactly
    one pass.
    """
    async with session.begin():
        ids = (await session.execute(BATCH_PICK_SQL)).scalars().all()
        if not ids:
            return 0

        processed = 0
        for ev_id in ids:
            event = await session.get(InboundWebhookEvent, ev_id)
            if event is None:
                # Row deleted between SELECT and SELECT-by-pk; nothing to do.
                continue
            handler = HANDLERS.get(event.event_type)
            if handler is None:
                # Unknown event type — mark processed with a note so we don't
                # loop on it forever; new event types can be added in code
                # without the dispatcher refusing to drain the queue.
                event.processed_at = datetime.now(timezone.utc)
                event.processing_error = f"no handler registered for {event.event_type!r}"
                processed += 1
                continue
            try:
                await handler(session, event)
            except Exception as exc:  # per-handler error isolation (Z4 §3.9)
                event.processing_error = repr(exc)
                # Leave processed_at NULL so the next tick retries (bounded
                # by the 24h received_at window in BATCH_PICK_SQL).
                logger.exception(
                    "[INBOUND-DISPATCH] handler failed event_id=%s type=%s",
                    event.event_id, event.event_type,
                )
            else:
                event.processed_at = datetime.now(timezone.utc)
                event.processing_error = None
                processed += 1
        return processed


async def _tick_once() -> int:
    async with async_session_maker() as session:
        return await process_one_batch(session)


async def run_dispatcher_loop(stop_event: asyncio.Event) -> None:
    """Run the dispatcher tick on `TICK_INTERVAL_SECONDS` cadence until
    `stop_event` is set. Shape mirrors a typical asyncio supervisor loop —
    the lifespan starts this as a task and `stop_event.set()` on shutdown.
    """
    logger.info("[INBOUND-DISPATCH] dispatcher started; tick=%ss", TICK_INTERVAL_SECONDS)
    while not stop_event.is_set():
        try:
            count = await _tick_once()
            if count:
                logger.info("[INBOUND-DISPATCH] processed %d events", count)
        except Exception:
            # Never let one bad tick kill the loop. The transaction inside
            # process_one_batch already rolled back.
            logger.exception("[INBOUND-DISPATCH] tick failed; continuing")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
    logger.info("[INBOUND-DISPATCH] dispatcher stopped")


# ---------- Receiver helper (called from the endpoint) ----------

async def insert_event_idempotent(
    session: AsyncSession,
    *,
    customer_id: UUID,
    source: str,
    event_id: str,
    event_type: str,
    payload: dict,
    correlation_id: UUID | None,
) -> bool:
    """Insert one inbound event with `ON CONFLICT (source, event_id) DO NOTHING`.

    Returns True if a new row was inserted, False if the same (source, event_id)
    already existed (dedup hit). The endpoint reports success either way per
    SHARED-CONTRACT §7.5 at-least-once contract.
    """
    stmt = text(
        """
        INSERT INTO inbound_webhook_events
            (customer_id, source, event_id, event_type, payload, correlation_id)
        VALUES
            (:customer_id, :source, :event_id, :event_type, CAST(:payload AS JSONB), :correlation_id)
        ON CONFLICT (source, event_id) DO NOTHING
        RETURNING id
        """
    )
    result = await session.execute(
        stmt,
        {
            "customer_id": str(customer_id),
            "source": source,
            "event_id": event_id,
            "event_type": event_type,
            "payload": json.dumps(payload),
            "correlation_id": str(correlation_id) if correlation_id else None,
        },
    )
    inserted_id = result.scalar_one_or_none()
    await session.commit()
    return inserted_id is not None
