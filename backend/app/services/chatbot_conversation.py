"""
Persistent conversation store for chatbot DMs.
Backed by PostgreSQL (chatbot_conversations table).
"""
import logging
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chatbot import ChatbotConversation
from app.config import get_settings

logger = logging.getLogger("zunkiree.chatbot.conversation")

settings = get_settings()


class ChatbotConversationService:

    async def get_history(
        self,
        db: AsyncSession,
        channel_id: UUID,
        sender_id: str,
        limit: int | None = None,
    ) -> list[dict]:
        """
        Fetch last N messages for this sender, ordered chronologically.
        Returns list of {"role": "user"|"assistant", "content": "..."}.
        """
        max_messages = limit or settings.chatbot_max_history
        result = await db.execute(
            select(ChatbotConversation)
            .where(
                ChatbotConversation.channel_id == channel_id,
                ChatbotConversation.platform_sender_id == sender_id,
            )
            .order_by(ChatbotConversation.created_at.desc())
            .limit(max_messages)
        )
        rows = result.scalars().all()
        # Reverse to chronological order
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    async def add_message(
        self,
        db: AsyncSession,
        channel_id: UUID,
        sender_id: str,
        role: str,
        content: str,
    ) -> None:
        """Persist a single message."""
        msg = ChatbotConversation(
            channel_id=channel_id,
            platform_sender_id=sender_id,
            role=role,
            content=content,
        )
        db.add(msg)
        await db.commit()

    async def cleanup_expired(self, db: AsyncSession) -> int:
        """Delete conversations older than TTL. Returns count deleted."""
        cutoff = datetime.utcnow() - timedelta(days=settings.chatbot_conversation_ttl_days)
        result = await db.execute(
            delete(ChatbotConversation).where(ChatbotConversation.created_at < cutoff)
        )
        await db.commit()
        count = result.rowcount
        if count:
            logger.info("Cleaned up %d expired chatbot conversations", count)
        return count


# Singleton
_conversation_service: ChatbotConversationService | None = None


def get_chatbot_conversation_service() -> ChatbotConversationService:
    global _conversation_service
    if _conversation_service is None:
        _conversation_service = ChatbotConversationService()
    return _conversation_service
