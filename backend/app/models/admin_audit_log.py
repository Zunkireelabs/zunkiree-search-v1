import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdminAuditLog(Base):
    """Forward-only audit trail of destructive admin actions (Z-Ops hardening).

    Written by `app.services.admin_audit.log_admin_action` from the destructive
    handlers in admin.py / admin_tenants.py / chatbot_admin.py. Helper failure
    is logged but never re-raised — the audit row is best-effort defense in
    depth, and must not be allowed to roll back the primary destructive op
    (which has already committed).
    """

    __tablename__ = "admin_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )

    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    target_table: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True,
    )
    target_site_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow,
    )
