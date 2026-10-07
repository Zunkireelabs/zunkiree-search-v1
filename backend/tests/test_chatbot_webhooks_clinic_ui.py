"""
SBAL-Z2: Instagram-native rendering of the clinic agent's structured `ui`
(services/slots/confirm/booking), driven with recorded-shape Meta webhook
payloads. Also pins the postback->exact-turn synthesis for the "Book this"
service card button, and that kasa/ecommerce's product-card rendering is
unchanged (the new `ui` branches are `elif`s after it).
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api import chatbot_webhooks as cw_module


# ---------------------------------------------------------------------------
# Postback -> exact-turn synthesis (no DB/network needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_book_service_postback_synthesizes_exact_turn_with_service_id_marker():
    entry = {
        "messaging": [
            {
                "sender": {"id": "ig-user-1"},
                "recipient": {"id": "page-1"},
                "postback": {
                    "payload": json.dumps({"action": "book_service", "service_id": "svc-abc", "name": "Lash Lift"}),
                },
            }
        ]
    }
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle:
        await cw_module._process_instagram_entry(entry)

    mock_handle.assert_awaited_once()
    kwargs = mock_handle.await_args.kwargs
    assert kwargs["message_text"] == "I'd like to book 'Lash Lift'. [service_id:svc-abc]"
    assert kwargs["is_postback"] is True


@pytest.mark.asyncio
async def test_add_to_cart_postback_unaffected_by_book_service_addition():
    """Regression: kasa's existing add_to_cart postback synthesis is untouched."""
    entry = {
        "messaging": [
            {
                "sender": {"id": "ig-user-2"},
                "recipient": {"id": "page-1"},
                "postback": {
                    "payload": json.dumps({"action": "add_to_cart", "product_id": "p1", "name": "White Shirt"}),
                },
            }
        ]
    }
    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle:
        await cw_module._process_instagram_entry(entry)

    kwargs = mock_handle.await_args.kwargs
    assert kwargs["message_text"] == "Add 'White Shirt' to my cart [product_id:p1]"


# ---------------------------------------------------------------------------
# `_handle_incoming_message` rendering — fake DB session, real control flow.
# ---------------------------------------------------------------------------


def _fake_channel():
    ch = MagicMock()
    ch.id = "chan-1"
    ch.customer_id = "cust-1"
    ch.page_access_token = "encrypted-token"
    ch.config = {}
    return ch


def _db_session(channel):
    channel_result = MagicMock()
    channel_result.scalar_one_or_none.return_value = channel

    db = AsyncMock()
    db.execute = AsyncMock(return_value=channel_result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


@asynccontextmanager
async def _session_cm(db):
    yield db


def _patched(db, process_message_result, meta_client):
    chatbot_service = MagicMock()
    chatbot_service.process_message = AsyncMock(return_value=process_message_result)
    return [
        patch.object(cw_module, "async_session_maker", lambda: _session_cm(db)),
        patch.object(cw_module, "decrypt_token", return_value="plain-token"),
        patch.object(cw_module, "get_meta_messaging_client", return_value=meta_client),
        patch.object(cw_module, "get_chatbot_query_service", return_value=chatbot_service),
    ]


def _meta_client():
    client = MagicMock()
    for m in ("mark_seen", "send_typing_on", "send_text_message", "send_chips",
              "send_service_cards", "send_service_detail", "send_booking_card",
              "send_product_cards", "send_suggestion_cards"):
        setattr(client, m, AsyncMock())
    return client


async def _run(process_message_result):
    channel = _fake_channel()
    db = _db_session(channel)
    meta_client = _meta_client()
    patches = _patched(db, process_message_result, meta_client)
    for p in patches:
        p.start()
    try:
        await cw_module._handle_incoming_message(
            platform="instagram",
            page_id="page-1",
            sender_id="ig-user-1",
            message_text="What services do you offer?",
            message_id=None,
        )
    finally:
        for p in patches:
            p.stop()
    return meta_client


@pytest.mark.asyncio
async def test_services_ui_renders_service_cards():
    result = {
        "answer": "Here's what we offer.",
        "suggestions": [],
        "ui": {"services": [{"id": "s1", "name": "Lash Lift", "price": 2500, "duration": 60,
                              "image_url": None, "description": "d"}]},
        "response_time_ms": 10,
        "query_log_id": None,
    }
    client = await _run(result)
    client.send_service_cards.assert_awaited_once()
    assert client.send_service_cards.await_args.kwargs["services"] == result["ui"]["services"]
    client.send_booking_card.assert_not_awaited()
    client.send_chips.assert_not_awaited()
    # SBAL-Z3 P3: a fixed one-line lead-in, never a (possibly truncated,
    # possibly differently-ordered) list of services duplicating the cards.
    client.send_text_message.assert_awaited_once()
    assert client.send_text_message.await_args.kwargs["text"] == "Here are our services — swipe to see them."


@pytest.mark.asyncio
async def test_slots_ui_renders_chips():
    slots = [{"label": "10:00", "payload": "Book Lash Lift on 2026-10-10 at 10:00"}]
    result = {
        "answer": "Here's what's open.",
        "suggestions": [],
        "ui": {"slots": slots},
        "response_time_ms": 10,
        "query_log_id": None,
    }
    client = await _run(result)
    client.send_chips.assert_awaited_once()
    assert client.send_chips.await_args.kwargs["chips"] == slots
    # SBAL-Z8 F3: no slots_prompt on `ui` (an older/unexpected shape) falls
    # back to the original English text rather than sending no text at all.
    assert client.send_chips.await_args.kwargs["text"] == "Pick a time:"


@pytest.mark.asyncio
async def test_slots_ui_chip_prompt_follows_conversation_language():
    slots = [{"label": "10:00", "payload": "Book Lash Lift on 2026-10-10 at 10:00"}]
    result = {
        "answer": "Yo samaya haru khali cha.",
        "suggestions": [],
        "ui": {"slots": slots, "slots_prompt": "Time chan-nuhos:"},
        "response_time_ms": 10,
        "query_log_id": None,
    }
    client = await _run(result)
    assert client.send_chips.await_args.kwargs["text"] == "Time chan-nuhos:"


@pytest.mark.asyncio
async def test_confirm_ui_renders_confirm_and_change_chips():
    confirm = {"summary": "Lash Lift on Sat at 10:00.", "yes_payload": "Yes", "change_payload": "I'd like to change the details"}
    result = {
        "answer": "Lash Lift on Sat at 10:00. Shall I book this?",
        "suggestions": [],
        "ui": {"confirm": confirm},
        "response_time_ms": 10,
        "query_log_id": None,
    }
    client = await _run(result)
    client.send_chips.assert_awaited_once()
    chips = client.send_chips.await_args.kwargs["chips"]
    assert chips == [
        {"label": "✅ Confirm", "payload": "Yes"},
        {"label": "✏️ Change", "payload": "I'd like to change the details"},
    ]
    # SBAL-Z3 P1: the summary (incl. "Shall I book this?") rides on the SAME
    # message as the chips — never sent again as a separate text bubble.
    assert client.send_chips.await_args.kwargs["text"] == result["answer"]
    client.send_text_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_booking_ui_renders_booking_card():
    booking = {"booking_number": "BK-999", "service": "Lash Lift", "when": "2026-10-10 10:00", "name": "Thamel Branch"}
    result = {
        "answer": "You're booked: Lash Lift on Saturday 10 October at 10:00 at Thamel Branch.",
        "suggestions": [],
        "ui": {"booking": booking},
        "response_time_ms": 10,
        "query_log_id": None,
    }
    client = await _run(result)
    client.send_booking_card.assert_awaited_once()
    assert client.send_booking_card.await_args.kwargs["booking"] == booking
    # the booking-truth sentence must NOT be shortened even though a card follows
    client.send_text_message.assert_awaited_once()
    assert client.send_text_message.await_args.kwargs["text"] == result["answer"]


@pytest.mark.asyncio
async def test_no_ui_falls_through_to_existing_product_cards_path():
    """Regression: kasa/ecommerce (no `ui` key at all) renders exactly as before."""
    products = [{"id": "p1", "name": "White Shirt", "price": 1500, "currency": "NPR", "images": []}]
    result = {
        "answer": "Here's the shirt.",
        "suggestions": [],
        "products": products,
        "response_time_ms": 10,
        "query_log_id": None,
    }
    client = await _run(result)
    client.send_product_cards.assert_awaited_once()
    assert client.send_product_cards.await_args.kwargs["products"] == products
    client.send_service_cards.assert_not_awaited()
    client.send_booking_card.assert_not_awaited()


# ---------------------------------------------------------------------------
# SBAL-Z5 F1/F2: single-service detail + localized carousel caption
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_detail_ui_renders_model_text_plus_book_button():
    """F1: a single-service match ("Details" tap, or any query resolving to
    exactly one service) is answered with the model's own text (already
    carrying price/duration) plus a single "Book this" button — never the
    one-card carousel / canned caption."""
    detail = {"id": "svc-xyz", "name": "Highly Defining Dye", "price": 1200,
              "duration": 45, "image_url": None, "description": "A bold brow tint."}
    result = {
        "answer": "Highly Defining Dye is NPR 1200 and takes about 45 minutes. It's a bold brow tint.",
        "suggestions": [],
        "ui": {"service_detail": detail},
        "response_time_ms": 10,
        "query_log_id": None,
    }
    client = await _run(result)
    client.send_service_cards.assert_not_awaited()
    client.send_chips.assert_not_awaited()
    client.send_service_detail.assert_awaited_once()
    kwargs = client.send_service_detail.await_args.kwargs
    assert kwargs["text"] == result["answer"]
    assert kwargs["service_id"] == "svc-xyz"
    assert kwargs["service_name"] == "Highly Defining Dye"
    # the plain-text send is skipped — text rides on the same message as the button
    client.send_text_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_detail_book_button_reaches_identical_booking_handling_as_carousel():
    """Brain review on #122: the service_detail "Book this" button and the
    carousel's own "Book this" button must produce the EXACT same postback
    payload, so both taps parse through the identical `action ==
    "book_service"` branch in `_process_instagram_entry` — one booking
    code path, not two differently-worded ones."""
    from app.services.meta_messaging import book_service_payload

    carousel_payload = book_service_payload("svc-xyz", "Highly Defining Dye")

    detail = {"id": "svc-xyz", "name": "Highly Defining Dye", "price": 1200,
              "duration": 45, "image_url": None, "description": "A bold brow tint."}
    result = {
        "answer": "Highly Defining Dye is NPR 1200.",
        "suggestions": [],
        "ui": {"service_detail": detail},
        "response_time_ms": 10,
        "query_log_id": None,
    }
    client = await _run(result)
    detail_kwargs = client.send_service_detail.await_args.kwargs

    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle:
        await cw_module._process_instagram_entry({
            "messaging": [{
                "sender": {"id": "ig-user-1"}, "recipient": {"id": "page-1"},
                "postback": {
                    "payload": book_service_payload(detail_kwargs["service_id"], detail_kwargs["service_name"]),
                    "mid": "mid-1",
                },
            }]
        })
    detail_turn_text = mock_handle.await_args.kwargs["message_text"]

    with patch.object(cw_module, "_handle_incoming_message", AsyncMock()) as mock_handle2:
        await cw_module._process_instagram_entry({
            "messaging": [{
                "sender": {"id": "ig-user-1"}, "recipient": {"id": "page-1"},
                "postback": {"payload": carousel_payload, "mid": "mid-2"},
            }]
        })
    carousel_turn_text = mock_handle2.await_args.kwargs["message_text"]

    assert carousel_payload == book_service_payload(detail_kwargs["service_id"], detail_kwargs["service_name"])
    assert detail_turn_text == carousel_turn_text == "I'd like to book 'Highly Defining Dye'. [service_id:svc-xyz]"


@pytest.mark.asyncio
async def test_services_ui_uses_localized_caption_when_present():
    """F2: when clinic_agent.py supplies a localized `services_caption`,
    that string is used verbatim instead of the hardcoded English one."""
    result = {
        "answer": "Hamro services haru yaha chan.",
        "suggestions": [],
        "ui": {
            "services": [{"id": "s1", "name": "Lash Lift", "price": 2500, "duration": 60,
                           "image_url": None, "description": "d"}],
            "services_caption": "Hamro services haru yaha chan — swipe garera hernuhos.",
        },
        "response_time_ms": 10,
        "query_log_id": None,
    }
    client = await _run(result)
    client.send_text_message.assert_awaited_once()
    assert client.send_text_message.await_args.kwargs["text"] == "Hamro services haru yaha chan — swipe garera hernuhos."


@pytest.mark.asyncio
async def test_services_ui_falls_back_to_english_caption_without_lang_key():
    """Regression: an older/bare `ui.services` payload with no caption key
    still gets the original English lead-in, not a KeyError or blank text."""
    result = {
        "answer": "Here's what we offer.",
        "suggestions": [],
        "ui": {"services": [{"id": "s1", "name": "Lash Lift", "price": 2500, "duration": 60,
                              "image_url": None, "description": "d"}]},
        "response_time_ms": 10,
        "query_log_id": None,
    }
    client = await _run(result)
    assert client.send_text_message.await_args.kwargs["text"] == "Here are our services — swipe to see them."
