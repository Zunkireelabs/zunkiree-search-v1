import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class BusinessProfile(Base):
    __tablename__ = "business_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Core business info
    business_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_model: Mapped[str | None] = mapped_column(String(20), nullable=True)  # B2C / B2B / B2B2C
    sales_approach: Mapped[str | None] = mapped_column(String(20), nullable=True)  # checkout / catalog / inquiry

    # Extracted fields (JSON stored as Text)
    services_products: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    pricing_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    policies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON object
    unique_selling_points: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional fields
    business_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    team_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Meta
    detected_tone: Mapped[str | None] = mapped_column(String(20), nullable=True)  # formal / neutral / friendly
    content_gaps: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    raw_extraction: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON — full LLM response

    # Pre-composed prompt block, ready to inject at query time
    system_prompt_block: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / building / completed / failed
    profile_locked: Mapped[bool] = mapped_column(Boolean, default=False)  # True = cloned from template, skip auto-build
    llm_tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="business_profile")


# Import at bottom to avoid circular imports
from app.models.customer import Customer
