import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text, Integer, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ChatbotChannel(Base):
    __tablename__ = "chatbot_channels"
    __table_args__ = (
        UniqueConstraint("platform", "platform_page_id", name="uq_chatbot_platform_page"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)  # instagram, messenger, whatsapp
    platform_page_id: Mapped[str] = mapped_column(String(255), nullable=False)
    page_access_token: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet-encrypted
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    channel_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    customer: Mapped["Customer"] = relationship(back_populates="chatbot_channels")
    conversations: Mapped[list["ChatbotConversation"]] = relationship(back_populates="channel", cascade="all, delete-orphan")
    message_logs: Mapped[list["ChatbotMessageLog"]] = relationship(back_populates="channel", cascade="all, delete-orphan")


class ChatbotConversation(Base):
    __tablename__ = "chatbot_conversations"
    __table_args__ = (
        Index("idx_chatbot_conv_channel_sender", "channel_id", "platform_sender_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chatbot_channels.id", ondelete="CASCADE"), nullable=False,
    )
    platform_sender_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    channel: Mapped["ChatbotChannel"] = relationship(back_populates="conversations")


class ChatbotMessageLog(Base):
    __tablename__ = "chatbot_message_log"
    __table_args__ = (
        Index("idx_chatbot_msglog_customer", "customer_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chatbot_channels.id", ondelete="CASCADE"), nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False,
    )
    platform_sender_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # inbound, outbound
    message_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_log_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("query_logs.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    channel: Mapped["ChatbotChannel"] = relationship(back_populates="message_logs")


from app.models.customer import Customer
