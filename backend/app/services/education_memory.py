"""
Persistent memory for the education agent: the student's profile and the chat
transcript (with the UI blocks shown).

Two backends behind the same interface: `DbEducationMemory` (production, per
request) and `InMemoryEducationMemory` (tests). Replaces the per-process
ConversationStore for this agent, so history survives restarts and multiple
workers, and a page reload can re-render the exact blocks the student saw.
"""
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.education_memory import VisitorProfile, WidgetMessage
from app.schemas.ui_blocks import upgrade_stored_block
from app.services.education_profile import new_profile

# visitor_profiles.session_id and widget_messages.session_id are VARCHAR(100) (migration 042).
SESSION_ID_MAX_LEN = 100


def is_valid_session_id(session_id) -> bool:
    """Every row here is keyed by (tenant, session_id), so a blank id would put every visitor without one in a single
    shared profile. Not forced to be a UUID: the widget sends crypto.randomUUID(), other callers may not."""
    return isinstance(session_id, str) and bool(session_id.strip()) and len(session_id) <= SESSION_ID_MAX_LEN


HISTORY_FOR_LLM = 10
HISTORY_FOR_WIDGET = 50
BLOCK_LOOKUP_WINDOW = HISTORY_FOR_WIDGET   # a tap can only come from a block the widget can show


def shown_titles(messages: list[dict]) -> list[str]:
    """Titles of the cards the student has seen, oldest first. Passed to the LLM as a system note,
    never inside message text (the model copies markers it finds in history into its replies)."""
    return [b["title"] for m in messages for b in (m.get("blocks") or []) if b.get("title")]


def _email_of(profile: dict) -> str | None:
    email = (profile.get("contact") or {}).get("email")
    return email.strip().lower() if email else None


class DbEducationMemory:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def load_profile(self, customer_id: uuid.UUID, session_id: str) -> dict:
        row = (await self.db.execute(
            select(VisitorProfile).where(VisitorProfile.customer_id == customer_id,
                                         VisitorProfile.session_id == session_id)
        )).scalar_one_or_none()
        profile = dict(row.profile) if row else new_profile()
        profile.setdefault("contact", {})
        profile.setdefault("shown", {})
        return profile

    async def save_profile(self, customer_id: uuid.UUID, session_id: str, profile: dict) -> None:
        row = (await self.db.execute(
            select(VisitorProfile).where(VisitorProfile.customer_id == customer_id,
                                         VisitorProfile.session_id == session_id)
        )).scalar_one_or_none()
        if row is None:
            row = VisitorProfile(customer_id=customer_id, session_id=session_id, profile=profile)
            self.db.add(row)
        else:
            row.profile = profile  # reassign so the JSONB change is detected
        row.email = _email_of(profile)
        await self.db.commit()

    async def find_profile_by_email(self, customer_id: uuid.UUID, email: str, exclude_session: str) -> dict | None:
        row = (await self.db.execute(
            select(VisitorProfile)
            .where(VisitorProfile.customer_id == customer_id,
                   func.lower(VisitorProfile.email) == email.strip().lower(),
                   VisitorProfile.session_id != exclude_session)
            .order_by(VisitorProfile.updated_at.desc()).limit(1)
        )).scalar_one_or_none()
        return dict(row.profile) if row else None

    async def append_message(self, customer_id: uuid.UUID, session_id: str, role: str, content: str,
                             blocks: list[dict] | None = None) -> None:
        self.db.add(WidgetMessage(customer_id=customer_id, session_id=session_id, role=role,
                                  content=content, blocks=blocks or []))
        await self.db.commit()

    async def mark_answered(self, customer_id: uuid.UUID, session_id: str, block_id: str, values: dict) -> bool:
        """Record what the student submitted on a block, so a reload shows it collapsed to a summary."""
        for row in reversed(await self._recent(customer_id, session_id, 20)):
            if row.role == "assistant" and any(b.get("block_id") == block_id for b in row.blocks):
                row.blocks = [{**b, "answered": values} if b.get("block_id") == block_id else b for b in row.blocks]
                await self.db.commit()
                return True
        return False

    async def find_block(self, customer_id: uuid.UUID, session_id: str, block_id: str,
                         limit: int = BLOCK_LOOKUP_WINDOW) -> dict | None:
        """The most recent block with this id shown in this session (assistant messages only), or None."""
        for row in reversed(await self._recent(customer_id, session_id, limit)):
            if row.role == "assistant":
                for b in row.blocks:
                    if b.get("block_id") == block_id:
                        return upgrade_stored_block(b)
        return None

    async def _recent(self, customer_id: uuid.UUID, session_id: str, limit: int) -> list[WidgetMessage]:
        rows = (await self.db.execute(
            select(WidgetMessage)
            .where(WidgetMessage.customer_id == customer_id, WidgetMessage.session_id == session_id)
            .order_by(WidgetMessage.created_at.desc()).limit(limit)
        )).scalars().all()
        return list(reversed(rows))

    async def load_history(self, customer_id: uuid.UUID, session_id: str, limit: int = HISTORY_FOR_LLM):
        """(LLM-ready messages, titles of cards already shown)."""
        rows = await self._recent(customer_id, session_id, limit)
        return ([{"role": m.role, "content": m.content} for m in rows],
                shown_titles([{"blocks": m.blocks} for m in rows]))

    async def list_messages(self, customer_id: uuid.UUID, session_id: str, limit: int = HISTORY_FOR_WIDGET) -> list[dict]:
        return [{"id": str(m.id), "role": m.role, "content": m.content,
                 "blocks": [upgrade_stored_block(b) for b in m.blocks], "created_at": m.created_at.isoformat()}
                for m in await self._recent(customer_id, session_id, limit)]


class InMemoryEducationMemory:
    """Same interface, no DB. For tests."""

    def __init__(self):
        self.profiles: dict[tuple, dict] = {}
        self.messages: dict[tuple, list[dict]] = defaultdict(list)

    async def load_profile(self, customer_id, session_id) -> dict:
        profile = self.profiles.get((customer_id, session_id))
        return new_profile() if profile is None else profile

    async def save_profile(self, customer_id, session_id, profile) -> None:
        self.profiles[(customer_id, session_id)] = profile

    async def find_profile_by_email(self, customer_id, email, exclude_session) -> dict | None:
        for (cid, sid), p in self.profiles.items():
            if cid == customer_id and sid != exclude_session and _email_of(p) == email.strip().lower():
                return p
        return None

    async def append_message(self, customer_id, session_id, role, content, blocks=None) -> None:
        self.messages[(customer_id, session_id)].append({
            "id": str(uuid.uuid4()), "role": role, "content": content, "blocks": blocks or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    async def mark_answered(self, customer_id, session_id, block_id, values) -> bool:
        for msg in reversed(self.messages[(customer_id, session_id)][-20:]):
            if msg["role"] == "assistant" and any(b.get("block_id") == block_id for b in msg["blocks"]):
                msg["blocks"] = [{**b, "answered": values} if b.get("block_id") == block_id else b for b in msg["blocks"]]
                return True
        return False

    async def find_block(self, customer_id, session_id, block_id, limit: int = BLOCK_LOOKUP_WINDOW) -> dict | None:
        for msg in reversed(self.messages[(customer_id, session_id)][-limit:]):
            if msg["role"] == "assistant":
                for b in msg["blocks"]:
                    if b.get("block_id") == block_id:
                        return upgrade_stored_block(b)
        return None

    async def load_history(self, customer_id, session_id, limit: int = HISTORY_FOR_LLM):
        rows = self.messages[(customer_id, session_id)][-limit:]
        return [{"role": m["role"], "content": m["content"]} for m in rows], shown_titles(rows)

    async def list_messages(self, customer_id, session_id, limit: int = HISTORY_FOR_WIDGET) -> list[dict]:
        return [{**m, "blocks": [upgrade_stored_block(b) for b in m["blocks"]]}
                for m in self.messages[(customer_id, session_id)][-limit:]]
