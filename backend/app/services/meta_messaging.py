from __future__ import annotations
"""
Meta Messaging API client — send messages via Instagram, Messenger, and WhatsApp.
Handles HMAC signature verification and platform-specific send formats.
"""
import hmac
import hashlib
import logging

import httpx
from cryptography.fernet import Fernet

from app.config import get_settings

logger = logging.getLogger("zunkiree.meta_messaging")

settings = get_settings()

# Instagram/Messenger share the same Send API. WhatsApp is slightly different.
SEND_API_URLS = {
    "instagram": "https://graph.facebook.com/v19.0/{page_id}/messages",
    "messenger": "https://graph.facebook.com/v19.0/{page_id}/messages",
    "whatsapp": "https://graph.facebook.com/v19.0/{page_id}/messages",
}

# Instagram DM has a 1000-character limit per message
INSTAGRAM_CHAR_LIMIT = 1000


def verify_webhook_signature(payload: bytes, signature: str, app_secret: str) -> bool:
    """Verify X-Hub-Signature-256 HMAC from Meta webhook."""
    if not signature or not signature.startswith("sha256="):
        logger.warning("Missing or malformed signature: %r", signature[:50] if signature else None)
        return False
    expected = hmac.new(
        app_secret.strip().encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    result = hmac.compare_digest(f"sha256={expected}", signature)
    if not result:
        logger.warning("Signature mismatch: expected sha256=%s..., got %s...", expected[:12], signature[:19])
    return result


def encrypt_token(token: str) -> str:
    """Encrypt a page access token for storage."""
    key = settings.chatbot_encryption_key
    if not key:
        raise ValueError("chatbot_encryption_key is not configured")
    f = Fernet(key.encode("utf-8"))
    return f.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted: str) -> str:
    """Decrypt a page access token from storage."""
    key = settings.chatbot_encryption_key
    if not key:
        raise ValueError("chatbot_encryption_key is not configured")
    f = Fernet(key.encode("utf-8"))
    return f.decrypt(encrypted.encode("utf-8")).decode("utf-8")


async def get_instagram_profile(sender_id: str, access_token: str) -> dict | None:
    """Fetch IG sender's public profile (name + pic) via Graph API.

    Returns dict with keys 'name', 'profile_pic' on success; None on any error.
    """
    url = f"https://graph.facebook.com/v22.0/{sender_id}"
    params = {"fields": "name,username,profile_pic", "access_token": access_token}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.warning("[META-PROFILE] fetch failed status=%s sender=%s", resp.status_code, sender_id)
                return None
            data = resp.json()
            return {"name": data.get("name"), "username": data.get("username"), "profile_pic": data.get("profile_pic")}
    except Exception as e:
        logger.error("[META-PROFILE] fetch exception sender=%s err=%s", sender_id, e)
        return None


def _format_price_npr(value) -> str:
    """SBAL-Z3 P4: "3,499" not "3499.0" — a whole-NPR price (the only kind
    list_services/check_availability ever return, see clinicmd_client's/
    zennly_client's _clean_price) with a thousands separator and no
    trailing decimal, on cards and in any adapter-built text."""
    if value is None:
        return ""
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,}"
    return f"{int(value):,}"


def book_service_payload(service_id: str, name: str) -> str:
    """SBAL-Z5 F1 (brain review on #122): the ONE place that builds a
    "Book this" postback payload, so the carousel's button and the
    single-service `send_service_detail` button are byte-identical and
    both parse through the same `action == "book_service"` branch in
    `_process_instagram_entry`/`_process_messenger_entry`."""
    import json as _json
    return _json.dumps({"action": "book_service", "service_id": service_id or "", "name": (name or "")[:80]})


class MetaMessagingClient:
    """Send messages via Meta's Graph API (Instagram, Messenger, WhatsApp)."""

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=15.0)

    async def mark_seen(
        self,
        platform: str,
        page_id: str,
        access_token: str,
        recipient_id: str,
    ) -> None:
        """Mark the message as seen (blue double-tick)."""
        if platform == "whatsapp":
            return
        url = SEND_API_URLS[platform].format(page_id=page_id)
        payload = {
            "recipient": {"id": recipient_id},
            "sender_action": "mark_seen",
        }
        try:
            resp = await self._http.post(url, json=payload, params={"access_token": access_token})
            if resp.status_code != 200:
                logger.warning("mark_seen failed: %s %s", resp.status_code, resp.json())
            else:
                logger.info("mark_seen sent to %s", recipient_id)
        except Exception as e:
            logger.warning("mark_seen error: %s", e)

    async def send_typing_on(
        self,
        platform: str,
        page_id: str,
        access_token: str,
        recipient_id: str,
    ) -> None:
        """Send typing indicator so the user sees '...' while we process."""
        if platform == "whatsapp":
            return
        url = SEND_API_URLS[platform].format(page_id=page_id)
        payload = {
            "recipient": {"id": recipient_id},
            "sender_action": "typing_on",
        }
        try:
            resp = await self._http.post(url, json=payload, params={"access_token": access_token})
            if resp.status_code != 200:
                logger.warning("typing_on failed: %s %s", resp.status_code, resp.json())
            else:
                logger.info("typing_on sent to %s", recipient_id)
        except Exception as e:
            logger.warning("typing_on error: %s", e)

    async def send_text_message(
        self,
        platform: str,
        page_id: str,
        access_token: str,
        recipient_id: str,
        text: str,
    ) -> dict:
        """Send a text reply. Splits if exceeding platform character limit."""
        if platform == "whatsapp":
            return await self._send_whatsapp_text(page_id, access_token, recipient_id, text)

        # Instagram / Messenger share the same format
        chunks = self._split_text(text, INSTAGRAM_CHAR_LIMIT)
        result = None
        for chunk in chunks:
            url = SEND_API_URLS[platform].format(page_id=page_id)
            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": chunk},
            }
            resp = await self._http.post(
                url,
                json=payload,
                params={"access_token": access_token},
            )
            result = resp.json()
            if resp.status_code != 200:
                logger.error("Meta Send API error: %s %s", resp.status_code, result)
                return {"error": result, "status_code": resp.status_code}
        return result or {}

    async def send_quick_replies(
        self,
        platform: str,
        page_id: str,
        access_token: str,
        recipient_id: str,
        text: str,
        options: list[str],
    ) -> dict:
        """Send text with quick reply buttons (suggestions)."""
        if platform == "whatsapp":
            # WhatsApp doesn't support quick replies the same way; send as text
            combined = text + "\n\n" + "\n".join(f"- {opt}" for opt in options)
            return await self._send_whatsapp_text(page_id, access_token, recipient_id, combined)

        # Truncate text to leave room for quick replies
        truncated = text[:INSTAGRAM_CHAR_LIMIT - 50] if len(text) > INSTAGRAM_CHAR_LIMIT - 50 else text
        url = SEND_API_URLS[platform].format(page_id=page_id)
        quick_replies = [
            {"content_type": "text", "title": opt[:80], "payload": opt[:1000]}
            for opt in options[:13]  # Meta allows max 13 quick replies
        ]
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": truncated, "quick_replies": quick_replies},
        }
        resp = await self._http.post(
            url,
            json=payload,
            params={"access_token": access_token},
        )
        result = resp.json()
        if resp.status_code != 200:
            logger.error("Meta Send API error (quick_replies): %s %s", resp.status_code, result)
        return result

    async def send_suggestion_cards(
        self,
        platform: str,
        page_id: str,
        access_token: str,
        recipient_id: str,
        suggestions: list[str],
    ) -> dict:
        """Send suggestions as a horizontally scrollable Generic Template carousel."""
        if platform == "whatsapp":
            # WhatsApp doesn't support generic templates; send as text
            combined = "You can also ask:\n" + "\n".join(f"- {s}" for s in suggestions)
            return await self._send_whatsapp_text(page_id, access_token, recipient_id, combined)

        url = SEND_API_URLS[platform].format(page_id=page_id)
        elements = [
            {
                "title": s[:80],
                "buttons": [
                    {
                        "type": "postback",
                        "title": "Tap",
                        "payload": s[:1000],
                    }
                ],
            }
            for s in suggestions[:10]
        ]
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "generic",
                        "elements": elements,
                    },
                }
            },
        }
        resp = await self._http.post(
            url,
            json=payload,
            params={"access_token": access_token},
        )
        result = resp.json()
        if resp.status_code != 200:
            logger.error("Meta Send API error (suggestion_cards): %s %s", resp.status_code, result)
        return result

    async def send_chips(
        self,
        platform: str,
        page_id: str,
        access_token: str,
        recipient_id: str,
        text: str,
        chips: list[dict],
    ) -> dict:
        """Quick-reply chips with an independent label/payload per chip (e.g.
        a "10:00" slot chip whose payload is the exact next turn "Book X on Y
        at 10:00", or a "✅ Confirm" chip whose payload is just "Yes"). Plain
        `send_quick_replies` reuses one string as both; SBAL-Z2 clinic UI
        (services/slots/confirm/booking) needs them to differ."""
        if platform == "whatsapp":
            combined = text + "\n\n" + "\n".join(f"- {c['label']}" for c in chips)
            return await self._send_whatsapp_text(page_id, access_token, recipient_id, combined)

        truncated = text[:INSTAGRAM_CHAR_LIMIT - 50] if len(text) > INSTAGRAM_CHAR_LIMIT - 50 else text
        url = SEND_API_URLS[platform].format(page_id=page_id)
        quick_replies = [
            {"content_type": "text", "title": c["label"][:80], "payload": c["payload"][:1000]}
            for c in chips[:13]  # Meta allows max 13 quick replies
        ]
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": truncated, "quick_replies": quick_replies},
        }
        resp = await self._http.post(
            url,
            json=payload,
            params={"access_token": access_token},
        )
        result = resp.json()
        if resp.status_code != 200:
            logger.error("Meta Send API error (chips): %s %s", resp.status_code, result)
        return result

    async def send_service_cards(
        self,
        platform: str,
        page_id: str,
        access_token: str,
        recipient_id: str,
        services: list[dict],
    ) -> dict:
        """SBAL-Z2: clinic `ui.services` -> a generic-template carousel. Each
        service is {id, name, price, duration, image_url, description} (see
        clinic_agent._services_ui). "Book this"'s payload carries the
        service id alongside the name — chatbot_webhooks.py synthesizes the
        exact next turn from it (same [field:value] marker pattern as the
        ecommerce add_to_cart postback)."""
        if platform == "whatsapp":
            lines = [f"• {s['name']}" + (f" - NPR {_format_price_npr(s['price'])}" if s.get("price") else "") for s in services[:5]]
            return await self._send_whatsapp_text(page_id, access_token, recipient_id, "\n".join(lines))

        url = SEND_API_URLS[platform].format(page_id=page_id)
        elements = []
        for s in services[:10]:
            name = s.get("name", "")
            title = f"{name} · NPR {_format_price_npr(s['price'])}" if s.get("price") else name
            subtitle = f"{s['duration']} min" if s.get("duration") else ""
            element = {"title": title[:80], "subtitle": subtitle[:80]}
            if s.get("image_url"):
                element["image_url"] = s["image_url"]
            element["buttons"] = [
                {
                    "type": "postback",
                    "title": "Book this",
                    "payload": book_service_payload(s.get("id", ""), name),
                },
                {
                    "type": "postback",
                    "title": "Details",
                    "payload": f"Tell me more about {name}"[:1000],
                },
            ]
            elements.append(element)

        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {"template_type": "generic", "elements": elements},
                }
            },
        }
        resp = await self._http.post(url, json=payload, params={"access_token": access_token})
        result = resp.json()
        if resp.status_code != 200:
            logger.error("Meta Send API error (service_cards): %s %s", resp.status_code, result)
        return result

    async def send_service_detail(
        self,
        platform: str,
        page_id: str,
        access_token: str,
        recipient_id: str,
        text: str,
        service_id: str,
        service_name: str,
    ) -> dict:
        """SBAL-Z5 F1 (brain review on #122): a single-service match's
        "Book this" button must reach the EXACT same booking handling as
        the carousel's own "Book this" — same `book_service_payload`, so
        both postbacks parse identically in
        `_process_instagram_entry`/`_process_messenger_entry`. A button
        template (text + buttons, no image/subtitle) rather than a
        one-element generic carousel — that visual duplication (a single
        card restating the service) was exactly what F1 removed."""
        if platform == "whatsapp":
            return await self._send_whatsapp_text(page_id, access_token, recipient_id, text)

        url = SEND_API_URLS[platform].format(page_id=page_id)
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "button",
                        "text": text[:640],
                        "buttons": [
                            {
                                "type": "postback",
                                "title": "Book this",
                                "payload": book_service_payload(service_id, service_name),
                            },
                        ],
                    },
                }
            },
        }
        resp = await self._http.post(url, json=payload, params={"access_token": access_token})
        result = resp.json()
        if resp.status_code != 200:
            logger.error("Meta Send API error (service_detail): %s %s", resp.status_code, result)
        return result

    async def send_booking_card(
        self,
        platform: str,
        page_id: str,
        access_token: str,
        recipient_id: str,
        booking: dict,
    ) -> dict:
        """SBAL-Z2: clinic `ui.booking` -> a single generic-template card.
        `booking` is {booking_number, service, when, name} (see
        clinic_agent._booking_ui) — `name` is the branch/location."""
        if platform == "whatsapp":
            text = f"Booked: {booking.get('service')} on {booking.get('when')} at {booking.get('name')} (ref {booking.get('booking_number')})"
            return await self._send_whatsapp_text(page_id, access_token, recipient_id, text)

        url = SEND_API_URLS[platform].format(page_id=page_id)
        element = {
            "title": f"Booked: {booking.get('service', '')}"[:80],
            "subtitle": f"{booking.get('when', '')} · {booking.get('name', '')} · Ref {booking.get('booking_number', '')}"[:80],
        }
        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {"template_type": "generic", "elements": [element]},
                }
            },
        }
        resp = await self._http.post(url, json=payload, params={"access_token": access_token})
        result = resp.json()
        if resp.status_code != 200:
            logger.error("Meta Send API error (booking_card): %s %s", resp.status_code, result)
        return result

    async def send_product_cards(
        self,
        platform: str,
        page_id: str,
        access_token: str,
        recipient_id: str,
        products: list[dict],
    ) -> dict:
        """Send products as a carousel with images, name, price, and action button."""
        if platform == "whatsapp":
            lines = [f"• {p['name']} - {p.get('currency','')} {p.get('price','')}" for p in products[:5]]
            return await self._send_whatsapp_text(page_id, access_token, recipient_id, "\n".join(lines))

        import json as _json
        url = SEND_API_URLS[platform].format(page_id=page_id)
        elements = []
        for p in products[:10]:
            images = p.get("images", [])
            price = p.get("price")
            currency = p.get("currency", "")
            subtitle = f"{currency} {price}" if price else ""
            if p.get("original_price") and p["original_price"] > (price or 0):
                subtitle = f"{currency} {price} (was {currency} {p['original_price']})"

            element = {
                "title": p.get("name", "")[:80],
                "subtitle": subtitle[:80],
            }
            if images:
                element["image_url"] = images[0]
            if p.get("url"):
                element["default_action"] = {"type": "web_url", "url": p["url"]}

            element["buttons"] = [
                {
                    "type": "postback",
                    "title": "Add to Cart",
                    "payload": _json.dumps({"action": "add_to_cart", "product_id": p.get("id", ""), "name": p.get("name", "")[:80]}),
                },
                {
                    "type": "postback",
                    "title": "Details",
                    "payload": _json.dumps({"action": "details", "product_id": p.get("id", ""), "name": p.get("name", "")[:80]}),
                },
            ]
            elements.append(element)

        payload = {
            "recipient": {"id": recipient_id},
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "generic",
                        "elements": elements,
                    },
                }
            },
        }
        resp = await self._http.post(url, json=payload, params={"access_token": access_token})
        result = resp.json()
        if resp.status_code != 200:
            logger.error("Meta Send API error (product_cards): %s %s", resp.status_code, result)
        return result

    async def set_ice_breakers(
        self,
        page_id: str,
        access_token: str,
        questions: list[dict],
    ) -> dict:
        """SBAL-Z2 item 5: Instagram Messenger Profile API ice breakers —
        the "Book an appointment" / "Services & prices" / "Hours & location"
        starter chips shown before the visitor's first message. `questions`
        is [{"question": str, "payload": str}]. Idempotent: re-setting the
        same list on every call is the Messenger Profile API's own contract
        (replace, not append), so this is safe to re-run from a script."""
        url = f"https://graph.facebook.com/v22.0/{page_id}/messenger_profile"
        payload = {
            "platform": "instagram",
            "ice_breakers": [{"locale": "default", "call_to_actions": questions[:4]}],
        }
        resp = await self._http.post(url, json=payload, params={"access_token": access_token})
        result = resp.json()
        if resp.status_code != 200:
            logger.error("Meta Send API error (ice_breakers): %s %s", resp.status_code, result)
        return result

    async def _send_whatsapp_text(
        self, phone_number_id: str, access_token: str, recipient_id: str, text: str,
    ) -> dict:
        """WhatsApp uses a slightly different payload format."""
        url = SEND_API_URLS["whatsapp"].format(page_id=phone_number_id)
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_id,
            "type": "text",
            "text": {"body": text[:4096]},  # WhatsApp limit is 4096 chars
        }
        resp = await self._http.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        result = resp.json()
        if resp.status_code != 200:
            logger.error("WhatsApp Send API error: %s %s", resp.status_code, result)
        return result

    @staticmethod
    def _split_text(text: str, limit: int) -> list[str]:
        """Split text into chunks respecting character limit, breaking at sentence boundaries."""
        if len(text) <= limit:
            return [text]
        chunks = []
        while text:
            if len(text) <= limit:
                chunks.append(text)
                break
            # Find last sentence boundary within limit
            cut = text[:limit].rfind(". ")
            if cut == -1 or cut < limit // 2:
                cut = text[:limit].rfind(" ")
            if cut == -1:
                cut = limit
            else:
                cut += 1  # Include the space/period
            chunks.append(text[:cut].strip())
            text = text[cut:].strip()
        return chunks


# Singleton
_meta_client: MetaMessagingClient | None = None


def get_meta_messaging_client() -> MetaMessagingClient:
    global _meta_client
    if _meta_client is None:
        _meta_client = MetaMessagingClient()
    return _meta_client
