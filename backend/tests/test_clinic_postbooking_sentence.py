"""CLINIC-POSTBOOKING-SENTENCE: after confirm_booking succeeds the reply is
built by code from the confirmed record, never narrated by the model."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.widget_config import WidgetConfig
from app.services import clinic_agent, clinic_tools
from app.services.clinic_agent import _build_confirmation_sentence
from tests.test_clinic_booking_truth import _run, _service_for_responses, _stream, _stream_tool_call
from tests.test_clinic_confirm_intent import _PENDING, _seed

# 2026-09-22 is a Tuesday
CONF = {**_PENDING, "service_name": "General Dentistry", "branch_name": "Main Branch"}
CONFIG = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
OK = {"booking": {"booking_number": "BK-20260922-0001"}, "confirmed_pending": CONF}


@pytest.mark.parametrize("lang,parts", [
    ("en", ["General Dentistry", "Tuesday", "22", "September", "10:00"]),
    ("ne_devanagari", ["General Dentistry", "मंगलबार", "22", "September", "10:00", "बुक भयो"]),
    ("ne_romanized", ["General Dentistry", "Mangalbar", "22", "September", "10:00", "book bhayo"]),
])
def test_sentence_names_service_weekday_date_time(lang, parts):
    out = _build_confirmation_sentence(CONF, "BK-1", lang, "voice")
    for p in parts:
        assert p in out
    assert "2026-09-22" not in out


def test_reference_chat_only_and_switchable(monkeypatch):
    assert "BK-1" in _build_confirmation_sentence(CONF, "BK-1", "en", "chat")
    assert "BK-1" not in _build_confirmation_sentence(CONF, "BK-1", "en", "voice")
    monkeypatch.setattr(clinic_agent, "INCLUDE_BOOKING_REF_IN_CHAT", False)
    assert "BK-1" not in _build_confirmation_sentence(CONF, "BK-1", "en", "chat")


def test_clinic_will_confirm_is_one_constant(monkeypatch):
    assert "clinic will confirm" in _build_confirmation_sentence(CONF, None, "en", "voice")
    monkeypatch.setattr(clinic_agent, "_CLINIC_WILL_CONFIRM", {"en": ""})
    assert "confirm" not in _build_confirmation_sentence(CONF, None, "en", "voice")


def _service(responses, saved):
    svc = _service_for_responses(responses)
    svc.conversation_store.add_message = lambda sid, role, text: saved.append((role, text))
    return svc


async def _forced(sid, channel="chat", saved=None):
    _seed(sid)
    clinic_agent._TURN_COUNTERS[sid] = 1
    # Any model response would raise IndexError: the model must not be asked.
    svc = _service([], saved if saved is not None else [])
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=OK)):
        return await _run(svc, CONFIG, "Yes, please book it.", session_id=sid, channel=channel)


async def _in_loop(sid, tool_result=OK, channel="chat", saved=None):
    clinic_tools.reset_session_state(sid)
    svc = _service([_stream_tool_call("c1", "confirm_booking", "{}")], saved if saved is not None else [])
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=tool_result)):
        return await _run(svc, CONFIG, "sure thing, book it", session_id=sid, channel=channel)


def _answer(events):
    return next(e for e in events if e["type"] == "done")["answer"]


@pytest.mark.asyncio
async def test_forced_and_in_loop_paths_produce_same_sentence_and_persist():
    s1, s2 = [], []
    a = _answer(await _forced(f"t-{uuid.uuid4()}", saved=s1))
    b = _answer(await _in_loop(f"t-{uuid.uuid4()}", saved=s2))
    assert a == b
    assert "General Dentistry" in a and "Tuesday" in a and "BK-20260922-0001" in a
    assert ("assistant", a) in s1 and ("assistant", b) in s2


@pytest.mark.asyncio
async def test_voice_omits_reference():
    assert "BK-" not in _answer(await _forced(f"t-{uuid.uuid4()}", channel="voice"))


@pytest.mark.asyncio
async def test_duplicate_yes_already_booked_still_true_sentence():
    res = {**OK, "already_booked": True}
    a = _answer(await _in_loop(f"t-{uuid.uuid4()}", tool_result=res))
    assert "You're booked" in a and "General Dentistry" in a


@pytest.mark.asyncio
@pytest.mark.parametrize("err", [
    {"error": "NEEDS_CONFIRMATION", "message": "x"},
    {"error": "SLOT_TAKEN", "message": "taken", "alternatives": []},
    {"error": "BOOKING_FAILED", "message": "x"},
    {"error": "NO_PENDING_BOOKING", "message": "x"},
])
async def test_confirm_failure_never_says_booked(err):
    sid = f"t-{uuid.uuid4()}"
    clinic_tools.reset_session_state(sid)
    svc = _service([_stream_tool_call("c1", "confirm_booking", "{}"), _stream("Sorry, that slot is gone.")], [])
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=err)):
        a = _answer(await _run(svc, CONFIG, "sure thing, book it", session_id=sid))
    assert "You're booked" not in a and a == "Sorry, that slot is gone."
