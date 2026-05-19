from __future__ import annotations
"""Cache of Meta-fetched sender profiles, keyed by (channel_id, platform_sender_id)."""
import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chatbot import ChatbotChannel
from app.models.chatbot_sender_profile import ChatbotSenderProfile
from app.services.meta_messaging import decrypt_token, get_instagram_profile

logger = logging.getLogger("zunkiree.sender_profile")


class SenderProfileService:
    async def get_or_fetch(
        self,
        db: AsyncSession,
        channel: ChatbotChannel,
        platform_sender_id: str,
    ) -> ChatbotSenderProfile | None:
        """Return cached profile, fetching from Meta if not yet cached or name is null."""
        result = await db.execute(
            select(ChatbotSenderProfile).where(
                ChatbotSenderProfile.channel_id == channel.id,
                ChatbotSenderProfile.platform_sender_id == platform_sender_id,
            )
        )
        profile = result.scalar_one_or_none()
        if profile and profile.name:
            return profile

        try:
            access_token = decrypt_token(channel.page_access_token)
        except Exception as e:
            logger.error("[SENDER-PROFILE] token decrypt failed channel=%s: %s", channel.id, e)
            return None

        meta_data = await get_instagram_profile(platform_sender_id, access_token)

        if not profile:
            profile = ChatbotSenderProfile(
                channel_id=channel.id,
                platform_sender_id=platform_sender_id,
            )
            db.add(profile)

        if meta_data and (meta_data.get("name") or meta_data.get("username")):
            profile.name = meta_data.get("name")
            profile.username = meta_data.get("username")
            profile.profile_pic_url = meta_data.get("profile_pic")
            profile.fetched_at = datetime.utcnow()
            profile.fetch_failed_at = None
            profile.fetch_error = None
        else:
            profile.fetch_failed_at = datetime.utcnow()
            profile.fetch_error = "Meta API returned no name or failed"

        await db.commit()
        return profile if (profile.name or profile.username) else None

    async def get_by_customer_and_sender_id(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        platform_sender_id: str,
    ) -> ChatbotSenderProfile | None:
        """Read cached profile (no API call). Used in order sync path.
        Returns the profile row if it exists, regardless of whether name/username are populated."""
        result = await db.execute(
            select(ChatbotSenderProfile)
            .join(ChatbotChannel, ChatbotSenderProfile.channel_id == ChatbotChannel.id)
            .where(
                ChatbotChannel.customer_id == customer_id,
                ChatbotSenderProfile.platform_sender_id == platform_sender_id,
            )
        )
        return result.scalar_one_or_none()


_service: SenderProfileService | None = None


def get_sender_profile_service() -> SenderProfileService:
    global _service
    if _service is None:
        _service = SenderProfileService()
    return _service
