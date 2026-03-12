"""
Per-session conversation memory store for multi-turn shopping conversations.
In-memory with 4-hour TTL.
"""
import time
import logging
from collections import defaultdict

logger = logging.getLogger("zunkiree.conversation")

TTL_SECONDS = 4 * 60 * 60  # 4 hours


class ConversationStore:
    def __init__(self):
        self._store: dict[str, dict] = {}

    def _ensure_session(self, session_id: str) -> dict:
        now = time.time()
        if session_id not in self._store or (now - self._store[session_id]["last_access"]) > TTL_SECONDS:
            self._store[session_id] = {
                "messages": [],
                "last_access": now,
            }
        self._store[session_id]["last_access"] = now
        return self._store[session_id]

    def get_messages(self, session_id: str) -> list[dict]:
        """Get conversation messages for a session."""
        session = self._ensure_session(session_id)
        return session["messages"]

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Add a message to the conversation."""
        session = self._ensure_session(session_id)
        session["messages"].append({"role": role, "content": content})
        # Keep last 20 messages to limit context size
        if len(session["messages"]) > 20:
            session["messages"] = session["messages"][-20:]

    def add_tool_call(self, session_id: str, tool_call: dict) -> None:
        """Add a tool call to the conversation."""
        session = self._ensure_session(session_id)
        session["messages"].append({
            "role": "assistant",
            "tool_calls": [tool_call],
            "content": None,
        })

    def add_tool_result(self, session_id: str, tool_call_id: str, result: str) -> None:
        """Add a tool result to the conversation."""
        session = self._ensure_session(session_id)
        session["messages"].append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        })

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count removed."""
        now = time.time()
        expired = [sid for sid, data in self._store.items() if (now - data["last_access"]) > TTL_SECONDS]
        for sid in expired:
            del self._store[sid]
        return len(expired)


# Singleton
_conversation_store: ConversationStore | None = None


def get_conversation_store() -> ConversationStore:
    global _conversation_store
    if _conversation_store is None:
        _conversation_store = ConversationStore()
    return _conversation_store
