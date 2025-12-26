import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    site_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    api_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    domains: Mapped[list["Domain"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    widget_config: Mapped["WidgetConfig"] = relationship(back_populates="customer", uselist=False, cascade="all, delete-orphan")
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    document_chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    query_logs: Mapped[list["QueryLog"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


# Import at bottom to avoid circular imports
from app.models.domain import Domain
from app.models.widget_config import WidgetConfig
from app.models.ingestion import IngestionJob, DocumentChunk
from app.models.query_log import QueryLog
