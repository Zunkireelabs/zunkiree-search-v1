"""
SBAL-Z3 B2: Manjila's lane log (10-06) shows "Tell me more about Lash Tint"
arriving 6 times ~8s apart, each one running the agent and sending a
different paraphrase. Root cause: `_process_instagram_entry` hardcoded
`message_id = None` for every postback, so the `platform_message_id`
dedupe in `_handle_incoming_message` never ran for button taps. Two
independent fixes: (1) use the postback's own `mid` so that dedupe now
applies to a genuine Meta redelivery; (2) a same-sender, same-payload,
20s debounce that catches a re-tap even when Meta hands it a fresh mid
each time (the tap gives no visual feedback and the reply takes 2-4s).
"""
import json
from unittest.mock import AsyncMock, patch

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


@pytest.fixture(autouse=True)
def _reset_debounce_store():
    cw_module._recent_postbacks.clear()
    yield
    cw_module._recent_postbacks.clear()


@pytest.mark.asyncio
async def test_identical_postback_within_20s_is_dropped_after_the_first():
    payload = json.dumps({"action": "details", "name": "Lash Tint"})
    t = {"now": 1000.0}
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle, \
         patch.object(cw_module.time, "monotonic", lambda: t["now"]):
        await cw_module._process_instagram_entry(_entry("sender-1", payload, "mid-1"))
        t["now"] += 8
        await cw_module._process_instagram_entry(_entry("sender-1", payload, "mid-2"))
        t["now"] += 8
        await cw_module._process_instagram_entry(_entry("sender-1", payload, "mid-3"))

    assert mock_handle.await_count == 1


@pytest.mark.asyncio
async def test_identical_postback_after_20s_is_not_dropped():
    payload = json.dumps({"action": "details", "name": "Lash Tint"})
    t = {"now": 1000.0}
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle, \
         patch.object(cw_module.time, "monotonic", lambda: t["now"]):
        await cw_module._process_instagram_entry(_entry("sender-1", payload, "mid-1"))
        t["now"] += 21
        await cw_module._process_instagram_entry(_entry("sender-1", payload, "mid-2"))
        t["now"] += 21
        await cw_module._process_instagram_entry(_entry("sender-1", payload, "mid-3"))

    assert mock_handle.await_count == 3


@pytest.mark.asyncio
async def test_different_senders_never_debounce_each_other():
    payload = json.dumps({"action": "details", "name": "Lash Tint"})
    t = {"now": 1000.0}
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle, \
         patch.object(cw_module.time, "monotonic", lambda: t["now"]):
        await cw_module._process_instagram_entry(_entry("sender-1", payload, "mid-1"))
        await cw_module._process_instagram_entry(_entry("sender-2", payload, "mid-2"))

    assert mock_handle.await_count == 2


@pytest.mark.asyncio
async def test_different_payload_same_sender_never_debounces():
    t = {"now": 1000.0}
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle, \
         patch.object(cw_module.time, "monotonic", lambda: t["now"]):
        await cw_module._process_instagram_entry(
            _entry("sender-1", json.dumps({"action": "details", "name": "Lash Tint"}), "mid-1")
        )
        t["now"] += 2
        await cw_module._process_instagram_entry(
            _entry("sender-1", json.dumps({"action": "details", "name": "Brow Lift"}), "mid-2")
        )

    assert mock_handle.await_count == 2


@pytest.mark.asyncio
async def test_postback_message_id_is_the_real_mid_not_none():
    payload = json.dumps({"action": "details", "name": "Lash Tint"})
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle:
        await cw_module._process_instagram_entry(_entry("sender-1", payload, "real-mid-123"))

    assert mock_handle.await_args.kwargs["message_id"] == "real-mid-123"


@pytest.mark.asyncio
async def test_text_messages_are_never_debounced():
    """Text messages are not debounced — only postbacks (brief item 2)."""
    entry = {
        "messaging": [
            {"sender": {"id": "sender-1"}, "recipient": {"id": "page-1"},
             "message": {"text": "hi", "mid": "m1"}},
        ]
    }
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle:
        await cw_module._process_instagram_entry(entry)
        await cw_module._process_instagram_entry(entry)

    assert mock_handle.await_count == 2


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


# --- Messenger twin ---


def _messenger_entry(sender_id, payload, mid):
    return {
        "messaging": [
            {
                "sender": {"id": sender_id},
                "recipient": {"id": "page-1"},
                "postback": {"payload": payload, "mid": mid},
            }
        ]
    }


@pytest.mark.asyncio
async def test_messenger_postback_debounce_mirrors_instagram():
    payload = json.dumps({"action": "details", "name": "White Shirt"})
    t = {"now": 2000.0}
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle, \
         patch.object(cw_module.time, "monotonic", lambda: t["now"]):
        await cw_module._process_messenger_entry(_messenger_entry("sender-9", payload, "mid-a"))
        t["now"] += 5
        await cw_module._process_messenger_entry(_messenger_entry("sender-9", payload, "mid-b"))

    assert mock_handle.await_count == 1
    assert mock_handle.await_args.kwargs["message_id"] == "mid-a"
