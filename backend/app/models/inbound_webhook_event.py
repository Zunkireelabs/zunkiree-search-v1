"""
InboundWebhookEvent — append-only ledger of signed deliveries from Stella
(and future provider webhooks).

Mirrors migration 032_inbound_webhook_events.sql. The (source, event_id)
unique constraint is the deduplication primitive for SHARED-CONTRACT.md
§7.5 at-least-once delivery: the receiver INSERTs with `ON CONFLICT (source,
event_id) DO NOTHING` and the second delivery becomes a no-op.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InboundWebhookEvent(Base):
    __tablename__ = "inbound_webhook_events"
    __table_args__ = (
        UniqueConstraint("source", "event_id", name="uq_inbound_events_source_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source: Mapped[str] = mapped_column(String(40), nullable=False)
    event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)

    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
