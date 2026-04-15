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
                        "title": "Ask",
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
