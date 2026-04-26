import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TenantBackendCredentials(Base):
    __tablename__ = "tenant_backend_credentials"
    __table_args__ = (
        UniqueConstraint("customer_id", "backend_type", name="uq_tbc_customer_backend"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    backend_type: Mapped[str] = mapped_column(String(40), nullable=False)
    remote_site_id: Mapped[str] = mapped_column(String(255), nullable=False)

    sync_key_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sync_key_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    sync_key_id_standby: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sync_key_secret_standby_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    webhook_signing_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    extra_config: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow,
    )

    customer: Mapped["Customer"] = relationship(back_populates="backend_credentials")


# Late import to avoid circular dep
from app.models.customer import Customer  # noqa: E402
