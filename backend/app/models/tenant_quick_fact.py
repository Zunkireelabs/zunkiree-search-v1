import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TenantQuickFact(Base):
    """A per-tenant static Q&A fact (hours/address/contact/staff/services
    overview/policy) that clinic_tools.py's search_knowledge fast-path
    matches against before falling through to the RAG pipeline. See
    migrations/038_tenant_quick_facts.sql and ZUNKIREE-FAST-FACTS-BRIEF."""

    __tablename__ = "tenant_quick_facts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True,
    )

    category: Mapped[str] = mapped_column(String(30), nullable=False)
    keywords: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow,
    )
