import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TenantOutboundWebhook(Base):
    """Stella-side receiver subscriptions for events Zunkiree fires per
    SHARED-CONTRACT §12.5 (lead.captured, query.logged,
    order.created.via_widget). Z6 ships registration only; emission lands in
    Z7. Soft-revoke via revoked_at preserves an audit trail of past signing
    secrets for delivered events.
    """

    __tablename__ = "tenant_outbound_webhooks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    events: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    signing_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    signing_secret_prefix: Mapped[str] = mapped_column(String(16), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="outbound_webhooks")


from app.models.customer import Customer  # noqa: E402
