"""
Meta webhook handler — receives Instagram, Messenger, and WhatsApp DMs.
Returns 200 OK immediately and processes messages in background.
"""
import hashlib
import logging
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.database import async_session_maker
from app.config import get_settings
from app.services.meta_messaging import verify_webhook_signature, decrypt_token, get_meta_messaging_client
from app.services.chatbot_query import get_chatbot_query_service
from app.models.chatbot import ChatbotChannel, ChatbotMessageLog

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("zunkiree.chatbot.webhook")

router = APIRouter(prefix="/webhooks/meta", tags=["chatbot-webhooks"])
settings = get_settings()


def _secret_fingerprint(secret: str) -> str:
    """Return a non-sensitive fingerprint of an app secret for log diagnostics."""
    digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    last4 = secret[-4:] if len(secret) >= 4 else "????"
    return f"sha256={digest[:8]}... len={len(secret)} last4=...{last4}"


# Log fingerprint at startup so drift is visible without exposing the secret.
if settings.meta_app_secret:
    logger.info("META_APP_SECRET fingerprint: %s", _secret_fingerprint(settings.meta_app_secret))
else:
    logger.error("META_APP_SECRET is empty — HMAC verification will 503 on every POST /webhooks/meta")

# Cache last product results per sender for size quick replies
_last_products: dict[str, list[dict]] = {}

# Pending add-to-cart: keyed by "page_id:sender_id" → product_id
# Set when user taps a carousel "Add to Cart" button; consumed when user replies with a size.
_pending_cart_add: dict[str, str] = {}


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

    # Verify HMAC signature — fail closed (Z-Ops hardening, #16). Empty
    # META_APP_SECRET is operator misconfiguration, returned as 503 so the
    # caller (Meta retry queue) backs off rather than treating it as auth
    # failure. Mismatch is 403 with a JSON envelope.
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not settings.meta_app_secret:
        logger.error("META_APP_SECRET not configured — webhook rejected (fail-closed)")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "service_unavailable",
                "message": "Webhook signature verification is not configured",
            },
        )
    if not verify_webhook_signature(payload, signature, settings.meta_app_secret):
        # Extract diagnostic fields from the untrusted payload so mismatches
        # are self-diagnosing in prod logs (#44). Parsed for logging only —
        # the request is still rejected below regardless of what's in the body.
        _diag_obj, _diag_entry = "?", "?"
        try:
            import json as _j
            _d = _j.loads(payload)
            _diag_obj = _d.get("object", "?")
            _entries = _d.get("entry", [])
            _diag_entry = str(_entries[0].get("id", "?")) if _entries else "?"
        except Exception:
            pass
        _client_ip = request.client.host if request.client else "unknown"
        _body_sha256 = hashlib.sha256(payload).hexdigest()
        _content_len = request.headers.get("Content-Length", "?")
        _content_enc = request.headers.get("Content-Encoding", "none")
        logger.warning(
            "Invalid webhook signature from %s — object=%s entry_id=%s "
            "body_sha256=%s... content-length=%s content-encoding=%s "
            "secret_fingerprint=[%s] — rejecting",
            _client_ip, _diag_obj, _diag_entry,
            _body_sha256[:16], _content_len, _content_enc,
            _secret_fingerprint(settings.meta_app_secret),
        )
        raise HTTPException(
            status_code=403,
            detail={"code": "invalid_signature"},
        )

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
        attachments = message.get("attachments", [])

        if not sender_id:
            continue

        page_id = event.get("recipient", {}).get("id")

        # Handle postback from suggestion/product card buttons (Generic Template)
        postback = event.get("postback", {})
        if postback.get("payload"):
            raw_payload = postback["payload"]
            message_id = None

            # Check if payload is a JSON action (e.g. product card buttons)
            import json as _postback_json
            try:
                action_data = _postback_json.loads(raw_payload)
                if isinstance(action_data, dict):
                    action = action_data.get("action")
                    if action == "add_to_cart":
                        pid = action_data["product_id"]
                        name = action_data.get("name", "")
                        label = f"'{name}'" if name else f"product {pid}"
                        message_text = f"Add {label} to my cart [product_id:{pid}]"
                        # Remember which product so the size reply can bypass the agent
                        _pending_cart_add[f"{page_id}:{sender_id}"] = pid
                    elif action == "details":
                        message_text = f"Tell me more about {action_data.get('name', 'this product')}"
                    else:
                        message_text = raw_payload
                else:
                    message_text = raw_payload
            except (ValueError, KeyError):
                message_text = raw_payload

            await _handle_incoming_message(
                platform="instagram",
                page_id=page_id,
                sender_id=sender_id,
                message_text=message_text,
                message_id=message_id,
                is_postback=True,
            )
            continue

        # If user tapped a quick reply, use the full payload as the message
        quick_reply = message.get("quick_reply", {})
        is_quick_reply = False
        if quick_reply.get("payload"):
            message_text = quick_reply["payload"]
            is_quick_reply = True

        # Handle shared posts: extract URL from attachments
        if not message_text and attachments:
            for att in attachments:
                att_type = att.get("type")
                att_url = att.get("payload", {}).get("url", "")
                if att_type == "share" and att_url:
                    message_text = f"[Shared post: {att_url}] I want to know about this"
                    break
                elif att_type in ("image", "video", "sticker", "audio"):
                    await _send_unsupported_type_reply(
                        platform="instagram", page_id=page_id,
                        sender_id=sender_id,
                    )
                    continue

        if not message_text:
            continue  # Skip reactions, read receipts, etc.

        await _handle_incoming_message(
            platform="instagram",
            page_id=page_id,
            sender_id=sender_id,
            message_text=message_text,
            message_id=message_id,
            is_quick_reply=is_quick_reply,
        )


async def _process_messenger_entry(entry: dict):
    """Extract and process Facebook Messenger messages."""
    messaging_events = entry.get("messaging", [])
    for event in messaging_events:
        sender_id = event.get("sender", {}).get("id")
        message = event.get("message", {})
        message_text = message.get("text")
        message_id = message.get("mid")
        attachments = message.get("attachments", [])

        if not sender_id:
            continue

        page_id = event.get("recipient", {}).get("id")

        # Handle postback from suggestion/product card buttons
        postback = event.get("postback", {})
        if postback.get("payload"):
            raw_payload = postback["payload"]
            message_id = None
            import json as _postback_json
            try:
                action_data = _postback_json.loads(raw_payload)
                if isinstance(action_data, dict):
                    action = action_data.get("action")
                    if action == "add_to_cart":
                        pid = action_data["product_id"]
                        name = action_data.get("name", "")
                        label = f"'{name}'" if name else f"product {pid}"
                        message_text = f"Add {label} to my cart [product_id:{pid}]"
                        _pending_cart_add[f"{page_id}:{sender_id}"] = pid
                    elif action == "details":
                        message_text = f"Tell me more about {action_data.get('name', 'this product')}"
                    else:
                        message_text = raw_payload
                else:
                    message_text = raw_payload
            except (ValueError, KeyError):
                message_text = raw_payload
            await _handle_incoming_message(
                platform="messenger",
                page_id=page_id,
                sender_id=sender_id,
                message_text=message_text,
                message_id=message_id,
                is_postback=True,
            )
            continue

        # If user tapped a quick reply, use the full payload as the message
        quick_reply = message.get("quick_reply", {})
        if quick_reply.get("payload"):
            message_text = quick_reply["payload"]

        # Handle shared posts/links
        if not message_text and attachments:
            for att in attachments:
                att_type = att.get("type")
                att_url = att.get("payload", {}).get("url", "")
                if att_type in ("share", "fallback") and att_url:
                    message_text = f"[Shared link: {att_url}] I want to know about this"
                    break

        if not message_text:
            continue

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
    is_postback: bool = False,
    is_quick_reply: bool = False,
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

            # Direct add-to-cart bypasses — skip agent when we already know the product.
            pkey = f"{page_id}:{sender_id}"
            pending_pid = _pending_cart_add.pop(pkey, None)

            if pending_pid and is_postback:
                # User tapped "Add to Cart" from carousel. Check if product has sizes.
                sender_key = f"{channel.id}:{sender_id}"
                product_sizes = []
                for p in _last_products.get(sender_key, []):
                    if str(p.get("id", "")) == str(pending_pid):
                        product_sizes = [s.strip() for s in p.get("sizes", []) if s and s.strip()]
                        break

                if product_sizes:
                    # Re-arm pending so the next size quick-reply tap triggers direct add.
                    _pending_cart_add[pkey] = pending_pid
                    size_prompt = "What size would you like?"
                    try:
                        await client.send_quick_replies(
                            platform=platform, page_id=send_page_id,
                            access_token=access_token, recipient_id=sender_id,
                            text=size_prompt, options=product_sizes[:13],
                        )
                    except Exception:
                        await client.send_text_message(
                            platform=platform, page_id=send_page_id,
                            access_token=access_token, recipient_id=sender_id,
                            text=size_prompt + " Options: " + ", ".join(product_sizes[:13]),
                        )
                    bot_reply = size_prompt
                else:
                    # No sizes — add directly without prompting.
                    from app.services.tools import execute_tool
                    from app.services.cart import get_cart_service
                    from app.models import Customer
                    from app.services.chatbot_conversation import get_chatbot_conversation_service
                    customer = await db.get(Customer, channel.customer_id)
                    site_id = customer.site_id if customer else ""
                    session_id = f"dm:{channel.id}:{sender_id}"
                    await get_cart_service().load_from_db(db, session_id)
                    add_result = await execute_tool(
                        tool_name="add_to_cart",
                        tool_args={"product_id": pending_pid, "size": ""},
                        db=db, session_id=session_id,
                        customer_id=channel.customer_id, site_id=site_id,
                    )
                    bot_reply = add_result.get("message", "Added to your cart!")
                    conv = get_chatbot_conversation_service()
                    await conv.add_message(db, channel.id, sender_id, "user", message_text)
                    await conv.add_message(db, channel.id, sender_id, "assistant", bot_reply)
                    await client.send_text_message(
                        platform=platform, page_id=send_page_id,
                        access_token=access_token, recipient_id=sender_id, text=bot_reply,
                    )

                outbound_log = ChatbotMessageLog(
                    channel_id=channel.id, customer_id=channel.customer_id,
                    platform_sender_id=sender_id, direction="outbound", message_text=bot_reply,
                )
                db.add(outbound_log)
                await db.commit()
                return

            elif pending_pid and is_quick_reply:
                # Only treat as a size tap if the text actually matches one of the
                # product's sizes. Chips like "Show my cart" / "Checkout" must fall
                # through to the agent, not be used as a size string.
                sender_key = f"{channel.id}:{sender_id}"
                product_sizes_upper = []
                for p in _last_products.get(sender_key, []):
                    if str(p.get("id", "")) == str(pending_pid):
                        product_sizes_upper = [s.strip().upper() for s in p.get("sizes", []) if s and s.strip()]
                        break

                if message_text.strip().upper() in product_sizes_upper:
                    from app.services.tools import execute_tool
                    from app.services.cart import get_cart_service
                    from app.models import Customer
                    from app.services.chatbot_conversation import get_chatbot_conversation_service
                    customer = await db.get(Customer, channel.customer_id)
                    site_id = customer.site_id if customer else ""
                    session_id = f"dm:{channel.id}:{sender_id}"
                    await get_cart_service().load_from_db(db, session_id)
                    add_result = await execute_tool(
                        tool_name="add_to_cart",
                        tool_args={"product_id": pending_pid, "size": message_text.strip()},
                        db=db, session_id=session_id,
                        customer_id=channel.customer_id, site_id=site_id,
                    )

                    # Build richer confirmation with cart summary + CTA chips
                    size_tapped = message_text.strip()
                    product_name = next(
                        (p.get("name", "") for p in _last_products.get(sender_key, [])
                         if str(p.get("id", "")) == str(pending_pid)),
                        "",
                    )
                    cart_data = add_result.get("cart", {})
                    item_count = cart_data.get("item_count", 1)
                    subtotal = cart_data.get("subtotal", 0)
                    currency = cart_data.get("currency", "NPR")

                    ch_config = channel.config if isinstance(channel.config, dict) else {}
                    preferred_lang = ch_config.get("preferred_language", "en")

                    if preferred_lang in {"ne_romanized", "mixed_ne_en"}:
                        bot_reply = (
                            f"✓ {product_name} (Size {size_tapped}) tapaiko cart ma add bhayo!\n"
                            f"Cart: {item_count} item, {currency} {subtotal:,.0f}"
                        )
                        chips = ["Checkout", "Cart hernu", "Aru herne"]
                    else:
                        bot_reply = (
                            f"✓ Added: {product_name} (Size {size_tapped})\n"
                            f"Cart: {item_count} item{'s' if item_count != 1 else ''}, "
                            f"{currency} {subtotal:,.0f}"
                        )
                        chips = ["Checkout", "View Cart", "Keep Shopping"]

                    conv = get_chatbot_conversation_service()
                    await conv.add_message(db, channel.id, sender_id, "user", message_text)
                    await conv.add_message(db, channel.id, sender_id, "assistant", bot_reply)
                    await client.send_quick_replies(
                        platform=platform, page_id=send_page_id,
                        access_token=access_token, recipient_id=sender_id,
                        text=bot_reply, options=chips,
                    )
                    outbound_log = ChatbotMessageLog(
                        channel_id=channel.id, customer_id=channel.customer_id,
                        platform_sender_id=sender_id, direction="outbound", message_text=bot_reply,
                    )
                    db.add(outbound_log)
                    await db.commit()
                    return
                else:
                    # Not a size (e.g. "Show my cart", "Checkout") — re-arm and fall
                    # through to agent so it handles the real intent.
                    _pending_cart_add[pkey] = pending_pid

            # Clear any stale pending entry before handing off to agent — the agent
            # path will re-arm it if it decides to ask about size.
            _pending_cart_add.pop(pkey, None)

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
            products = result.get("products", [])
            response_time_ms = result.get("response_time_ms", 0)
            query_log_id = result.get("query_log_id")
            feedback_signal = result.get("feedback_signal")

            # If this was a feedback signal, update the previous query log
            if feedback_signal and query_log_id is None:
                await _update_feedback_from_signal(db, channel.id, sender_id, feedback_signal)

            # Cache products for size quick replies on follow-up turns
            sender_key = f"{channel.id}:{sender_id}"
            if products:
                _last_products[sender_key] = products

            # Detect if agent is asking about size — show sizes as quick replies
            answer_lower = answer.lower()
            size_question = any(phrase in answer_lower for phrase in [
                "what size", "which size", "size do you", "size would you",
                "size?", "pick a size", "choose a size", "select a size",
            ])
            available_sizes = []
            size_source = products or _last_products.get(sender_key, [])
            if size_question and size_source:
                for p in size_source:
                    for s in p.get("sizes", []):
                        if s not in available_sizes:
                            available_sizes.append(s)
                # Arm the pending cache so the user's size tap bypasses the agent.
                # Only applies when there's a single unambiguous product in context.
                if pkey not in _pending_cart_add and len(size_source) == 1:
                    _pending_cart_add[pkey] = size_source[0]["id"]

            # Decide what to attach to the answer message
            quick_reply_options = None
            if size_question and available_sizes:
                quick_reply_options = available_sizes[:13]
            elif suggestions and len(suggestions) > 0 and not products:
                trimmed = suggestions[:3]
                if all(len(s) <= 20 for s in trimmed):
                    quick_reply_options = trimmed

            # When a product carousel follows, shorten the text to one sentence
            # so text + carousel feel like one coherent reply rather than two
            # separate messages (#43). Full answer is preserved when no carousel.
            send_text = answer
            if products:
                dot_pos = answer.find(". ")
                if 0 < dot_pos < 200:
                    send_text = answer[:dot_pos + 1]
                elif len(answer) > 200:
                    send_text = answer[:200].rstrip() + "…"

            # Send answer — with quick replies attached if available
            if quick_reply_options:
                try:
                    await client.send_quick_replies(
                        platform=platform,
                        page_id=send_page_id,
                        access_token=access_token,
                        recipient_id=sender_id,
                        text=send_text,
                        options=quick_reply_options,
                    )
                except Exception:
                    await client.send_text_message(
                        platform=platform,
                        page_id=send_page_id,
                        access_token=access_token,
                        recipient_id=sender_id,
                        text=send_text,
                    )
            else:
                await client.send_text_message(
                    platform=platform,
                    page_id=send_page_id,
                    access_token=access_token,
                    recipient_id=sender_id,
                    text=send_text,
                )

            # Send product cards if the agent returned products
            if products:
                try:
                    await client.send_product_cards(
                        platform=platform,
                        page_id=send_page_id,
                        access_token=access_token,
                        recipient_id=sender_id,
                        products=products[:5],
                    )
                except Exception as e:
                    logger.warning("Product cards failed: %s", e)

            # Carousel cards for longer suggestions (no separate emoji message)
            elif suggestions and len(suggestions) > 0 and not quick_reply_options:
                try:
                    await client.send_suggestion_cards(
                        platform=platform,
                        page_id=send_page_id,
                        access_token=access_token,
                        recipient_id=sender_id,
                        suggestions=suggestions[:3],
                    )
                except Exception as e:
                    logger.warning("Suggestions failed: %s", e)

            # Log outbound message
            outbound_log = ChatbotMessageLog(
                channel_id=channel.id,
                customer_id=channel.customer_id,
                platform_sender_id=sender_id,
                direction="outbound",
                message_text=answer,
                response_time_ms=response_time_ms,
                query_log_id=query_log_id,
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


async def _send_unsupported_type_reply(
    platform: str,
    page_id: str | None,
    sender_id: str,
):
    """Send a polite reply when we receive an unsupported attachment type."""
    async with async_session_maker() as db:
        try:
            result = await db.execute(
                select(ChatbotChannel).where(
                    ChatbotChannel.platform == platform,
                    ChatbotChannel.platform_page_id == page_id,
                    ChatbotChannel.is_active == True,
                )
            )
            channel = result.scalar_one_or_none()
            if not channel:
                return

            import json as _json
            access_token = decrypt_token(channel.page_access_token)
            client = get_meta_messaging_client()
            send_page_id = page_id
            if platform == "instagram" and channel.config:
                try:
                    config = _json.loads(channel.config) if isinstance(channel.config, str) else channel.config
                    send_page_id = config.get("facebook_page_id", page_id)
                except Exception:
                    pass

            await client.send_text_message(
                platform=platform,
                page_id=send_page_id,
                access_token=access_token,
                recipient_id=sender_id,
                text="I can read text messages and shared posts right now. Could you type out your question instead?",
            )
        except Exception as e:
            logger.warning("Failed to send unsupported-type reply: %s", e)


async def _update_feedback_from_signal(
    db: AsyncSession,
    channel_id,
    sender_id: str,
    signal: str,
):
    """Update the most recent query log with feedback from a natural language signal."""
    from app.models import QueryLog
    from datetime import datetime

    try:
        # Find the most recent outbound message for this sender
        result = await db.execute(
            select(ChatbotMessageLog).where(
                ChatbotMessageLog.channel_id == channel_id,
                ChatbotMessageLog.platform_sender_id == sender_id,
                ChatbotMessageLog.direction == "outbound",
            ).order_by(ChatbotMessageLog.created_at.desc()).limit(1)
        )
        last_outbound = result.scalar_one_or_none()
        if not last_outbound:
            return

        # If we have a linked query_log_id, update its feedback
        if hasattr(last_outbound, 'query_log_id') and last_outbound.query_log_id:
            log = await db.get(QueryLog, last_outbound.query_log_id)
            if log:
                log.feedback_vote = 1 if signal == "positive" else -1
                log.feedback_at = datetime.utcnow()
                await db.commit()
                logger.info("Updated feedback for query_log %s: %s", log.id, signal)
    except Exception as e:
        logger.warning("Failed to update feedback from signal: %s", e)
