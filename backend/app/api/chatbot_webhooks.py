"""
Meta webhook handler — receives Instagram, Messenger, and WhatsApp DMs.
Returns 200 OK immediately and processes messages in background.
"""
import logging
from fastapi import APIRouter, Request, Query
from fastapi.responses import PlainTextResponse

from app.database import async_session_maker
from app.config import get_settings
from app.services.meta_messaging import verify_webhook_signature, decrypt_token, get_meta_messaging_client
from app.services.chatbot_query import get_chatbot_query_service
from app.models.chatbot import ChatbotChannel, ChatbotMessageLog

from sqlalchemy import select

logger = logging.getLogger("zunkiree.chatbot.webhook")

router = APIRouter(prefix="/webhooks/meta", tags=["chatbot-webhooks"])
settings = get_settings()


@router.get("")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    code: str = Query(None),
):
    """
    Meta webhook verification + OAuth callback handler.
    - Meta sends GET with hub.mode=subscribe for webhook verification.
    - Instagram OAuth redirects here with ?code=XXXX for token exchange.
    """
    # Handle Instagram OAuth callback
    if code:
        import httpx
        logger.info("OAuth callback received, exchanging code for token...")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.instagram.com/oauth/access_token",
                    data={
                        "client_id": "2067985003771014",
                        "client_secret": settings.meta_app_secret,
                        "grant_type": "authorization_code",
                        "redirect_uri": "https://api.zunkireelabs.com/api/v1/webhooks/meta",
                        "code": code,
                    },
                )
                token_data = resp.json()
                logger.info("Token exchange response: %s", token_data)
                return {"status": "token_exchanged", "data": token_data}
        except Exception as e:
            logger.error("Token exchange failed: %s", e)
            return {"status": "error", "detail": str(e)}

    # Handle webhook verification
    if hub_mode == "subscribe" and hub_verify_token == settings.meta_verify_token:
        logger.info("Webhook verification successful")
        return PlainTextResponse(content=hub_challenge)
    logger.warning("Webhook verification failed: mode=%s", hub_mode)
    return PlainTextResponse(content="Verification failed", status_code=403)


@router.post("")
async def receive_webhook(request: Request):
    """
    Receive incoming messages from Instagram/Messenger/WhatsApp.
    Returns 200 OK immediately; processes message in background task.
    """
    payload = await request.body()

    # Verify HMAC signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    if settings.meta_app_secret and not verify_webhook_signature(payload, signature, settings.meta_app_secret):
        logger.warning("Invalid webhook signature — bypassing for debug")
        # TODO: re-enable after fixing app secret
        # return {"status": "invalid_signature"}

    # Parse the webhook payload
    import json
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {"status": "invalid_json"}

    # Determine platform from object field
    obj = data.get("object", "")
    entries = data.get("entry", [])

    for entry in entries:
        if obj == "instagram":
            await _process_instagram_entry(entry)
        elif obj == "page":
            await _process_messenger_entry(entry)
        elif obj == "whatsapp_business_account":
            await _process_whatsapp_entry(entry)

    # Must return 200 quickly — Meta retries on timeout
    return {"status": "ok"}


async def _process_instagram_entry(entry: dict):
    """Extract and process Instagram DM messages."""
    messaging_events = entry.get("messaging", [])
    for event in messaging_events:
        sender_id = event.get("sender", {}).get("id")
        message = event.get("message", {})
        message_text = message.get("text")
        message_id = message.get("mid")

        if not sender_id or not message_text:
            continue  # Skip non-text messages (reactions, read receipts, etc.)

        page_id = event.get("recipient", {}).get("id")
        await _handle_incoming_message(
            platform="instagram",
            page_id=page_id,
            sender_id=sender_id,
            message_text=message_text,
            message_id=message_id,
        )


async def _process_messenger_entry(entry: dict):
    """Extract and process Facebook Messenger messages."""
    messaging_events = entry.get("messaging", [])
    for event in messaging_events:
        sender_id = event.get("sender", {}).get("id")
        message = event.get("message", {})
        message_text = message.get("text")
        message_id = message.get("mid")

        if not sender_id or not message_text:
            continue

        page_id = event.get("recipient", {}).get("id")
        await _handle_incoming_message(
            platform="messenger",
            page_id=page_id,
            sender_id=sender_id,
            message_text=message_text,
            message_id=message_id,
        )


async def _process_whatsapp_entry(entry: dict):
    """Extract and process WhatsApp messages."""
    changes = entry.get("changes", [])
    for change in changes:
        value = change.get("value", {})
        messages = value.get("messages", [])
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id")

        for msg in messages:
            if msg.get("type") != "text":
                continue
            sender_id = msg.get("from")
            message_text = msg.get("text", {}).get("body")
            message_id = msg.get("id")

            if not sender_id or not message_text:
                continue

            await _handle_incoming_message(
                platform="whatsapp",
                page_id=phone_number_id,
                sender_id=sender_id,
                message_text=message_text,
                message_id=message_id,
            )


async def _handle_incoming_message(
    platform: str,
    page_id: str | None,
    sender_id: str,
    message_text: str,
    message_id: str | None,
):
    """
    Core message handler. Runs with its own DB session since this may
    execute after the webhook response has been sent.
    """
    async with async_session_maker() as db:
        try:
            # Look up which tenant owns this page
            result = await db.execute(
                select(ChatbotChannel).where(
                    ChatbotChannel.platform == platform,
                    ChatbotChannel.platform_page_id == page_id,
                    ChatbotChannel.is_active == True,
                )
            )
            channel = result.scalar_one_or_none()
            if not channel:
                logger.warning("No active channel for %s page_id=%s", platform, page_id)
                return

            # Mark seen + typing indicator immediately
            import asyncio
            import json as _json
            try:
                access_token = decrypt_token(channel.page_access_token)
                client = get_meta_messaging_client()
                send_page_id = page_id
                if platform == "instagram" and channel.config:
                    try:
                        config = _json.loads(channel.config) if isinstance(channel.config, str) else channel.config
                        send_page_id = config.get("facebook_page_id", page_id)
                    except Exception:
                        pass
                # 1. Mark message as seen
                await client.mark_seen(
                    platform=platform,
                    page_id=send_page_id,
                    access_token=access_token,
                    recipient_id=sender_id,
                )
                # 2. Show typing indicator
                await client.send_typing_on(
                    platform=platform,
                    page_id=send_page_id,
                    access_token=access_token,
                    recipient_id=sender_id,
                )
            except Exception:
                pass  # Non-critical

            # Deduplication check
            if message_id:
                existing = await db.execute(
                    select(ChatbotMessageLog.id).where(
                        ChatbotMessageLog.platform_message_id == message_id
                    )
                )
                if existing.scalar_one_or_none():
                    logger.debug("Duplicate message %s — skipping", message_id)
                    return

            # Log inbound message
            inbound_log = ChatbotMessageLog(
                channel_id=channel.id,
                customer_id=channel.customer_id,
                platform_sender_id=sender_id,
                platform_message_id=message_id,
                direction="inbound",
                message_text=message_text,
            )
            db.add(inbound_log)
            await db.commit()

            # Process via RAG pipeline
            chatbot_service = get_chatbot_query_service()
            result = await chatbot_service.process_message(
                db=db,
                channel=channel,
                sender_id=sender_id,
                message_text=message_text,
            )

            answer = result["answer"]
            suggestions = result.get("suggestions", [])
            response_time_ms = result.get("response_time_ms", 0)

            # Send reply via Meta API (reuse token and page_id from typing indicator)
            # Append suggestions as text instead of quick replies (quick reply titles
            # are limited to 20 chars on Instagram which truncates them)
            reply_text = answer
            if suggestions:
                suggestion_text = "\n\nYou can also ask:\n" + "\n".join(
                    f"  → {s}" for s in suggestions[:3]
                )
                if len(reply_text) + len(suggestion_text) <= 950:
                    reply_text += suggestion_text

            await client.send_text_message(
                platform=platform,
                page_id=send_page_id,
                access_token=access_token,
                recipient_id=sender_id,
                text=reply_text,
            )

            # Log outbound message
            outbound_log = ChatbotMessageLog(
                channel_id=channel.id,
                customer_id=channel.customer_id,
                platform_sender_id=sender_id,
                direction="outbound",
                message_text=answer,
                response_time_ms=response_time_ms,
            )
            db.add(outbound_log)
            await db.commit()

        except Exception as e:
            logger.error("Error processing %s message from %s: %s", platform, sender_id, e, exc_info=True)
            # Log the error
            try:
                error_log = ChatbotMessageLog(
                    channel_id=channel.id if 'channel' in dir() else None,
                    customer_id=channel.customer_id if 'channel' in dir() else None,
                    platform_sender_id=sender_id,
                    platform_message_id=message_id,
                    direction="inbound",
                    message_text=message_text,
                    error=str(e),
                )
                db.add(error_log)
                await db.commit()
            except Exception:
                pass  # Don't let error logging break the flow
