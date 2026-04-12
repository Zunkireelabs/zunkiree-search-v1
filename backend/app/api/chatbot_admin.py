"""
Chatbot channel management — connect/disconnect messaging platforms per tenant.
Protected by X-Admin-Key header (same as other admin endpoints).
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Customer
from app.models.chatbot import ChatbotChannel, ChatbotConversation, ChatbotMessageLog
from app.services.meta_messaging import encrypt_token
from app.config import get_settings

logger = logging.getLogger("zunkiree.chatbot.admin")

router = APIRouter(prefix="/admin/chatbot", tags=["chatbot-admin"])
settings = get_settings()


async def verify_admin_key(x_admin_key: str = Header(...)):
    if x_admin_key != settings.api_secret_key:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "Invalid admin key"},
        )
    return x_admin_key


# --- Request/Response Models ---


class ConnectChannelRequest(BaseModel):
    site_id: str = Field(..., description="Tenant site_id to connect")
    platform: str = Field(..., pattern="^(instagram|messenger|whatsapp)$", description="Messaging platform")
    platform_page_id: str = Field(..., description="Instagram Business Account ID, FB Page ID, or WA Phone Number ID")
    page_access_token: str = Field(..., description="Long-lived Meta page access token")
    channel_name: str | None = Field(None, description="Human-friendly label (e.g., @mybusiness)")


class ChannelResponse(BaseModel):
    id: str
    platform: str
    platform_page_id: str
    channel_name: str | None
    is_active: bool
    created_at: str
    total_messages: int = 0


class ConversationSummary(BaseModel):
    platform_sender_id: str
    message_count: int
    last_message_at: str


# --- Endpoints ---


@router.post("/channels", dependencies=[Depends(verify_admin_key)])
async def connect_channel(
    request: ConnectChannelRequest,
    db: AsyncSession = Depends(get_db),
):
    """Connect a messaging platform account to a tenant."""
    # Validate customer exists
    result = await db.execute(
        select(Customer).where(Customer.site_id == request.site_id, Customer.is_active == True)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found or inactive")

    # Check for duplicate
    existing = await db.execute(
        select(ChatbotChannel).where(
            ChatbotChannel.platform == request.platform,
            ChatbotChannel.platform_page_id == request.platform_page_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This platform account is already connected")

    # Encrypt the token before storing
    encrypted_token = encrypt_token(request.page_access_token)

    channel = ChatbotChannel(
        customer_id=customer.id,
        platform=request.platform,
        platform_page_id=request.platform_page_id,
        page_access_token=encrypted_token,
        channel_name=request.channel_name,
        is_active=True,
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)

    logger.info("Connected %s channel for %s (channel=%s)", request.platform, request.site_id, channel.id)

    return {
        "id": str(channel.id),
        "platform": channel.platform,
        "platform_page_id": channel.platform_page_id,
        "channel_name": channel.channel_name,
        "is_active": channel.is_active,
        "created_at": channel.created_at.isoformat(),
    }


@router.get("/channels/{site_id}", dependencies=[Depends(verify_admin_key)])
async def list_channels(
    site_id: str,
    db: AsyncSession = Depends(get_db),
):
    """List all connected channels for a tenant."""
    result = await db.execute(
        select(Customer).where(Customer.site_id == site_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    channels_result = await db.execute(
        select(ChatbotChannel).where(ChatbotChannel.customer_id == customer.id)
    )
    channels = channels_result.scalars().all()

    response = []
    for ch in channels:
        # Get message count
        msg_count = await db.execute(
            select(func.count()).where(ChatbotMessageLog.channel_id == ch.id)
        )
        total = msg_count.scalar() or 0

        response.append({
            "id": str(ch.id),
            "platform": ch.platform,
            "platform_page_id": ch.platform_page_id,
            "channel_name": ch.channel_name,
            "is_active": ch.is_active,
            "created_at": ch.created_at.isoformat(),
            "total_messages": total,
        })

    return {"channels": response}


@router.delete("/channels/{channel_id}", dependencies=[Depends(verify_admin_key)])
async def disconnect_channel(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Disconnect a channel (soft delete — sets is_active=False)."""
    result = await db.execute(
        select(ChatbotChannel).where(ChatbotChannel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    channel.is_active = False
    await db.commit()

    logger.info("Disconnected channel %s (%s)", channel_id, channel.platform)
    return {"status": "disconnected", "channel_id": channel_id}


@router.get("/channels/{channel_id}/conversations", dependencies=[Depends(verify_admin_key)])
async def list_conversations(
    channel_id: str,
    db: AsyncSession = Depends(get_db),
):
    """View recent conversation threads for a channel."""
    result = await db.execute(
        select(ChatbotChannel).where(ChatbotChannel.id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    # Get unique senders with message count and last activity
    from sqlalchemy import desc
    senders = await db.execute(
        select(
            ChatbotConversation.platform_sender_id,
            func.count().label("message_count"),
            func.max(ChatbotConversation.created_at).label("last_message_at"),
        )
        .where(ChatbotConversation.channel_id == channel.id)
        .group_by(ChatbotConversation.platform_sender_id)
        .order_by(desc("last_message_at"))
        .limit(50)
    )

    conversations = [
        {
            "platform_sender_id": row.platform_sender_id,
            "message_count": row.message_count,
            "last_message_at": row.last_message_at.isoformat() if row.last_message_at else None,
        }
        for row in senders
    ]

    return {"channel_id": channel_id, "conversations": conversations}


@router.get("/channels/{channel_id}/conversations/{sender_id}", dependencies=[Depends(verify_admin_key)])
async def get_conversation_messages(
    channel_id: str,
    sender_id: str,
    db: AsyncSession = Depends(get_db),
):
    """View full conversation with a specific sender."""
    messages_result = await db.execute(
        select(ChatbotConversation)
        .where(
            ChatbotConversation.channel_id == channel_id,
            ChatbotConversation.platform_sender_id == sender_id,
        )
        .order_by(ChatbotConversation.created_at.asc())
        .limit(100)
    )
    messages = messages_result.scalars().all()

    return {
        "channel_id": channel_id,
        "sender_id": sender_id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ],
    }
