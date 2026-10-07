"""SBAL-Z4 (brain review on #120): the same GREETING_WORDS fast-path that
query.py had — and which #120 already fixed there — also existed in
ChatbotQueryService.process_message, the real Instagram DM webhook path.
A clinic tenant's bare "hi" must reach _process_booking_agent_message (the
clinic lane), not the generic "{brand}'s assistant" template, so the IG
first-greeting actually carries the tenant's assistant_name. Ecommerce/kasa
keeps the template byte-for-byte.

Also covers the brain's question: a clinic-type channel with NO booking
lane configured must still answer sanely, never crash or go silent —
_process_booking_agent_message already guards that (settings.clinic_lane_url
unset -> "booking isn't available right now" fallback); this test confirms
process_message's new fall-through actually reaches that guard rather than
bypassing it.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chatbot_query import ChatbotQueryService


def _make_service():
    svc = ChatbotQueryService.__new__(ChatbotQueryService)
    svc.conversation_service = MagicMock()
    svc.conversation_service.get_history = AsyncMock(return_value=[])
    svc.conversation_service.add_message = AsyncMock()
    svc.llm_service = MagicMock()
    return svc


def _make_channel(platform="instagram"):
    ch = MagicMock()
    ch.id = "ch-1"
    ch.config = {}
    ch.platform = platform
    return ch


def _make_customer(website_type):
    c = MagicMock()
    c.id = "cust-uuid"
    c.site_id = "sbal" if website_type == "clinic" else "kasa"
    c.name = "Test Co"
    c.is_active = True
    c.website_type = website_type
    return c


def _db_with_no_config():
    db = AsyncMock()
    db.get = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_clinic_bare_greeting_reaches_booking_agent_not_template():
    svc = _make_service()
    customer = _make_customer("clinic")
    db = _db_with_no_config()
    db.get.return_value = customer

    with patch.object(svc, "_process_booking_agent_message", new=AsyncMock(
        return_value={"answer": "booking lane response", "suggestions": [], "ui": None,
                       "response_time_ms": 1, "query_log_id": None},
    )) as mock_booking, \
         patch("app.services.chatbot_query.get_sender_profile_service") as mock_profile_svc:
        mock_profile_svc.return_value.get_or_fetch = AsyncMock(return_value=None)
        result = await svc.process_message(db=db, channel=_make_channel(), sender_id="sender-1", message_text="hi")

    assert mock_booking.called
    assert result["answer"] == "booking lane response"


@pytest.mark.asyncio
async def test_clinic_bare_greeting_without_lane_gets_sane_fallback_not_crash():
    """Confirms the brain's question: a clinic channel with no booking lane
    configured still answers sanely once "hi" falls through to the booking
    path — it never silently dead-ends or raises."""
    svc = _make_service()
    customer = _make_customer("clinic")
    db = _db_with_no_config()
    db.get.return_value = customer

    settings = MagicMock()
    settings.clinic_lane_url = None  # not configured

    with patch("app.services.chatbot_query.get_settings", return_value=settings), \
         patch("app.services.chatbot_query.get_sender_profile_service") as mock_profile_svc:
        mock_profile_svc.return_value.get_or_fetch = AsyncMock(return_value=None)
        result = await svc.process_message(db=db, channel=_make_channel(), sender_id="sender-1", message_text="hi")

    assert "booking isn't available right now" in result["answer"]


@pytest.mark.asyncio
async def test_ecommerce_bare_greeting_keeps_generic_template():
    svc = _make_service()
    customer = _make_customer("ecommerce")
    db = _db_with_no_config()
    db.get.return_value = customer

    with patch.object(svc, "_process_booking_agent_message", new=AsyncMock()) as mock_booking:
        result = await svc.process_message(db=db, channel=_make_channel(platform="chat"), sender_id="sender-1", message_text="hi")

    assert not mock_booking.called
    assert "Hi there! I'm Test Co's assistant." in result["answer"]
