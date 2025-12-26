import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, Text, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class WidgetConfig(Base):
    __tablename__ = "widget_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    brand_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tone: Mapped[str] = mapped_column(String(50), default="neutral")  # formal, neutral, friendly
    primary_color: Mapped[str] = mapped_column(String(7), default="#2563eb")
    placeholder_text: Mapped[str] = mapped_column(String(255), default="Ask a question...")
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_message: Mapped[str] = mapped_column(
        Text,
        default="I don't have that information yet. Please contact us directly for help."
    )
    allowed_topics: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string of topics
    max_response_length: Mapped[int] = mapped_column(Integer, default=500)
    show_sources: Mapped[bool] = mapped_column(Boolean, default=True)
    show_suggestions: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="widget_config")


from app.models.customer import Customer
