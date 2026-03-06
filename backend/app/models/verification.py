import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class VerificationSession(Base):
    __tablename__ = "verification_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(20), default="anonymous", nullable=False
    )  # anonymous, email_requested, code_sent, name_requested, fields_requested, verified
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verification_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    code_attempts: Mapped[int] = mapped_column(Integer, default=0)
    pending_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pending_custom_fields: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of remaining fields
    current_field_index: Mapped[int] = mapped_column(Integer, default=0)
    detected_intent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    intent_signup_fields: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of intent-specific fields
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
