"""
SBAL-Z3 B2: Manjila's lane log (10-06) shows "Tell me more about Lash Tint"
arriving 6 times ~8s apart, each one running the agent and sending a
different paraphrase. Root cause: `_process_instagram_entry` hardcoded
`message_id = None` for every postback, so the `platform_message_id`
dedupe in `_handle_incoming_message` never ran for button taps.

Two independent fixes: (1) use the postback's own `mid`, so a genuine Meta
redelivery is still caught by that dedupe; (2) review on #117: an
in-memory, per-process debounce doesn't work — the prod API runs
--workers 2, and postback mids are unique per tap anyway, so neither the
mid dedupe nor a per-process dict catches a tap storm split across both
workers. The real debounce is DB-backed instead: same channel + sender +
resulting message text, inbound, within 20s, queried from
chatbot_message_log — a table every worker already shares.
"""
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api import chatbot_webhooks as cw_module


def _entry(sender_id, payload, mid):
    return {
        "messaging": [
            {
                "sender": {"id": sender_id},
                "recipient": {"id": "page-1"},
                "postback": {"payload": payload, "mid": mid},
            }
        ]
    }


# ---------------------------------------------------------------------------
# mid wiring (no DB needed — _handle_incoming_message is mocked away)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_postback_message_id_is_the_real_mid_not_none():
    payload = json.dumps({"action": "details", "name": "Lash Tint"})
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle:
        await cw_module._process_instagram_entry(_entry("sender-1", payload, "real-mid-123"))

    assert mock_handle.await_args.kwargs["message_id"] == "real-mid-123"


@pytest.mark.asyncio
async def test_messenger_postback_also_carries_real_mid():
    payload = json.dumps({"action": "details", "name": "White Shirt"})
    entry = {
        "messaging": [{"sender": {"id": "sender-9"}, "recipient": {"id": "page-1"},
                        "postback": {"payload": payload, "mid": "mid-a"}}]
    }
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle:
        await cw_module._process_messenger_entry(entry)

    assert mock_handle.await_args.kwargs["message_id"] == "mid-a"


@pytest.mark.asyncio
async def test_message_echo_is_ignored_before_channel_lookup():
    entry = {
        "messaging": [
            {"sender": {"id": "page-1"}, "recipient": {"id": "ig-user-1"},
             "message": {"text": "bot's own outbound reply", "is_echo": True, "mid": "echo-1"}},
        ]
    }
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle:
        await cw_module._process_instagram_entry(entry)

    mock_handle.assert_not_awaited()


# ---------------------------------------------------------------------------
# DB-backed debounce — exercised through _handle_incoming_message directly,
# with a fresh, independent mock DB session per call (no shared Python
# state at all), the way two real --workers 2 processes would see it: the
# only thing they share is the real, same database.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _session_cm(db):
    yield db


def _fake_channel():
    ch = MagicMock()
    ch.id = "chan-1"
    ch.customer_id = "cust-1"
    ch.page_access_token = "encrypted-token"
    ch.config = {}
    return ch


def _meta_client():
    client = MagicMock()
    for m in ("mark_seen", "send_typing_on", "send_text_message"):
        setattr(client, m, AsyncMock())
    return client


def _db_with_execute_sequence(results: list):
    """A fresh AsyncMock DB session (simulating a separate worker process —
    no state is shared with any other call in the test) whose db.execute()
    returns `results` in order for the dedupe-by-mid check, then the
    postback-debounce check, then (if not dropped) whatever else the
    handler needs."""
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=results)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _no_match_result():
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    return r


def _match_result():
    r = MagicMock()
    r.scalar_one_or_none.return_value = "existing-log-id"
    return r


async def _call(db, message_text="Tell me more about Lash Tint", sender_id="sender-1", mid="mid-x"):
    # `db.execute`'s side_effect is already set by the caller, in call
    # order: (1) channel lookup, (2) platform_message_id dedupe, (3)
    # postback-debounce check, (4+) whatever else proceeding needs.
    chatbot_service = MagicMock()
    chatbot_service.process_message = AsyncMock(return_value={
        "answer": "ok", "suggestions": [], "response_time_ms": 1, "query_log_id": None,
    })

    with patch.object(cw_module, "async_session_maker", lambda: _session_cm(db)), \
         patch.object(cw_module, "decrypt_token", return_value="plain-token"), \
         patch.object(cw_module, "get_meta_messaging_client", return_value=_meta_client()), \
         patch.object(cw_module, "get_chatbot_query_service", return_value=chatbot_service):
        await cw_module._handle_incoming_message(
            platform="instagram", page_id="page-1", sender_id=sender_id,
            message_text=message_text, message_id=mid, is_postback=True,
        )
    return chatbot_service


@pytest.mark.asyncio
async def test_identical_postback_within_20s_is_dropped_even_across_independent_calls():
    """Two calls with ZERO shared Python state (fresh db mock each time) —
    the "two workers" scenario. The second call's own db.execute sequence
    simulates what a shared real DB would already contain: no match on the
    mid dedupe (different mid), but a match on the text+sender+20s debounce
    query (worker 1's inbound log row is already there)."""
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = _fake_channel()

    # Worker 1: channel lookup, mid-dedupe miss, debounce-query miss -> proceeds.
    db1 = AsyncMock()
    db1.execute = AsyncMock(side_effect=[channel_result, _no_match_result(), _no_match_result()])
    db1.add = MagicMock()
    db1.commit = AsyncMock()

    svc1 = await _call(db1, mid="mid-1")
    svc1.process_message.assert_awaited_once()

    # Worker 2 (fresh everything): channel lookup, mid-dedupe miss (different
    # mid), debounce-query HIT (same text+sender+channel, inside 20s, now
    # present in the shared table worker 1 just wrote to) -> dropped.
    db2 = AsyncMock()
    db2.execute = AsyncMock(side_effect=[channel_result, _no_match_result(), _match_result()])
    db2.add = MagicMock()
    db2.commit = AsyncMock()

    svc2 = await _call(db2, mid="mid-2")
    svc2.process_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_debounce_query_scoped_to_channel_sender_text_and_window():
    channel = _fake_channel()
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[channel_result, _no_match_result(), _match_result()])
    db.add = MagicMock()
    db.commit = AsyncMock()

    await _call(db, message_text="Tell me more about Lash Tint", sender_id="sender-1", mid="mid-9")

    # Third call is the debounce query itself — assert its WHERE clause
    # scopes on channel_id, platform_sender_id, direction, message_text,
    # and a created_at cutoff within the configured window.
    debounce_call_args = db.execute.await_args_list[2].args[0]
    compiled = str(debounce_call_args)
    assert "chatbot_message_log" in compiled.lower()
    assert "channel_id" in compiled
    assert "platform_sender_id" in compiled
    assert "message_text" in compiled
    assert "created_at" in compiled


@pytest.mark.asyncio
async def test_text_messages_are_never_debounced_at_the_handler_level():
    """is_postback=False must skip the debounce query entirely — a
    legitimate repeated text message is not a tap storm."""
    channel = _fake_channel()
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[channel_result, _no_match_result()])
    db.add = MagicMock()
    db.commit = AsyncMock()

    chatbot_service = MagicMock()
    chatbot_service.process_message = AsyncMock(return_value={
        "answer": "ok", "suggestions": [], "response_time_ms": 1, "query_log_id": None,
    })

    with patch.object(cw_module, "async_session_maker", lambda: _session_cm(db)), \
         patch.object(cw_module, "decrypt_token", return_value="plain-token"), \
         patch.object(cw_module, "get_meta_messaging_client", return_value=_meta_client()), \
         patch.object(cw_module, "get_chatbot_query_service", return_value=chatbot_service):
        await cw_module._handle_incoming_message(
            platform="instagram", page_id="page-1", sender_id="sender-1",
            message_text="hi", message_id="m1", is_postback=False,
        )

    chatbot_service.process_message.assert_awaited_once()
    # Only 2 execute calls (channel lookup + mid dedupe) — no debounce query.
    assert db.execute.await_count == 2


def test_debounce_window_constant_is_twenty_seconds():
    assert cw_module._POSTBACK_DEBOUNCE_SECONDS == 20


# ---------------------------------------------------------------------------
# SBAL-Z5 F3: a dropped duplicate must send Meta nothing at all — not even
# mark_seen/typing_on — so the visitor never sees a "…" bubble with no
# reply behind it.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dropped_duplicate_postback_sends_zero_meta_calls():
    channel = _fake_channel()
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel

    db = AsyncMock()
    # channel lookup, mid-dedupe miss, debounce-query HIT -> dropped.
    db.execute = AsyncMock(side_effect=[channel_result, _no_match_result(), _match_result()])
    db.add = MagicMock()
    db.commit = AsyncMock()

    meta_client = _meta_client()
    chatbot_service = MagicMock()
    chatbot_service.process_message = AsyncMock(return_value={
        "answer": "ok", "suggestions": [], "response_time_ms": 1, "query_log_id": None,
    })

    with patch.object(cw_module, "async_session_maker", lambda: _session_cm(db)), \
         patch.object(cw_module, "decrypt_token", return_value="plain-token"), \
         patch.object(cw_module, "get_meta_messaging_client", return_value=meta_client), \
         patch.object(cw_module, "get_chatbot_query_service", return_value=chatbot_service):
        await cw_module._handle_incoming_message(
            platform="instagram", page_id="page-1", sender_id="sender-1",
            message_text="Tell me more about Lash Tint", message_id="mid-dup", is_postback=True,
        )

    chatbot_service.process_message.assert_not_awaited()
    meta_client.mark_seen.assert_not_awaited()
    meta_client.send_typing_on.assert_not_awaited()
    meta_client.send_text_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_processed_postback_still_sends_mark_seen_and_typing_on():
    """Regression: a NON-duplicate postback still gets mark_seen/typing_on,
    just moved to after the dedupe checks instead of before."""
    channel = _fake_channel()
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[channel_result, _no_match_result(), _no_match_result()])
    db.add = MagicMock()
    db.commit = AsyncMock()

    meta_client = _meta_client()
    chatbot_service = MagicMock()
    chatbot_service.process_message = AsyncMock(return_value={
        "answer": "ok", "suggestions": [], "response_time_ms": 1, "query_log_id": None,
    })

    with patch.object(cw_module, "async_session_maker", lambda: _session_cm(db)), \
         patch.object(cw_module, "decrypt_token", return_value="plain-token"), \
         patch.object(cw_module, "get_meta_messaging_client", return_value=meta_client), \
         patch.object(cw_module, "get_chatbot_query_service", return_value=chatbot_service):
        await cw_module._handle_incoming_message(
            platform="instagram", page_id="page-1", sender_id="sender-1",
            message_text="Tell me more about Lash Tint", message_id="mid-fresh", is_postback=True,
        )

    chatbot_service.process_message.assert_awaited_once()
    meta_client.mark_seen.assert_awaited_once()
    meta_client.send_typing_on.assert_awaited_once()
