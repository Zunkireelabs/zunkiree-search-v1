import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ChatbotSenderProfile(Base):
    __tablename__ = "chatbot_sender_profiles"
    __table_args__ = (
        UniqueConstraint("channel_id", "platform_sender_id", name="chatbot_sender_profiles_unique"),
        Index("idx_chatbot_sender_profiles_channel_sender", "channel_id", "platform_sender_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chatbot_channels.id", ondelete="CASCADE"), nullable=False,
    )
    platform_sender_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_pic_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetch_failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetch_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    channel: Mapped["ChatbotChannel"] = relationship(back_populates="sender_profiles")


from app.models.chatbot import ChatbotChannel
