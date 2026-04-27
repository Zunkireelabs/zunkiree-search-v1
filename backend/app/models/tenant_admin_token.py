import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TenantAdminToken(Base):
    """Per-tenant admin token (zka_live_<id>, zka_sec_<48>) issued to Stella so
    it can call Zunkiree's per-tenant admin API on a merchant's behalf. The full
    secret is shown once at creation; only the Argon2id hash is stored.

    Max 2 active tokens per tenant is enforced by a database trigger
    (check_admin_token_limit, migration 034). Rotation creates a new row, then
    revokes the prior one after the 24h overlap window.
    """

    __tablename__ = "tenant_admin_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    token_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    secret_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    secret_hash: Mapped[str] = mapped_column(Text, nullable=False)

    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="admin_tokens")


from app.models.customer import Customer  # noqa: E402
