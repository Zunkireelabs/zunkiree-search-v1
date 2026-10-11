"""SBAL-Z10: spoken-phone fold on the inbound turn (F5), under-9-digit phones
rejected (F6), and the missing-details loop breaker counted at the re-ask
itself — including a model paraphrase with no tool call (F4)."""
import logging
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.widget_config import WidgetConfig
from app.services.conversation import get_conversation_store
from app.services.clinic_tools import (
    fold_spoken_phone_in_text, phone_is_plausible, reset_session_state, to_e164,
)
from tests.test_clinic_booking_flow_language_sbal_z8 import (
    _run, _service_for_responses, _stream, _stream_tool_call, _tool_exec_side_effect,
)

CONTACT = "01-4444444"


@pytest.mark.parametrize("raw,expected", [
    ("नौ आठ चार एक पाँच चार शून्य चार तीन चार", "9841540434"),
    ("नाइन एट फोर वन फाइभ फोर जिरो फोर थ्री फोर", "9841540434"),
    ("my number is nine eight four one five four zero four three four thanks", "my number is 9841540434 thanks"),
    ("९८४१५४०४३४", "9841540434"),
])
def test_fold_spoken_phone(raw, expected):
    out, changed = fold_spoken_phone_in_text(raw)
    assert out == expected and changed


@pytest.mark.parametrize("raw", [
    "", "I want two or three lashes", "one two three", "book at five thirty",
    "नौ आठ चार", "9841540434", "tomorrow at ten", "२०२६",
])
def test_fold_leaves_everything_else_alone(raw):
    out, changed = fold_spoken_phone_in_text(raw)
    assert out == raw and not changed


@pytest.mark.parametrize("raw", ["१२३", "१२३४", "12345", "12345678"])
def test_short_phone_is_implausible(raw):
    assert not phone_is_plausible(raw, to_e164(raw))


@pytest.mark.parametrize("raw", ["9841540434", "984154034", "+9779841540434", "९८४१५४०४३४"])
def test_real_phone_is_plausible(raw):
    assert phone_is_plausible(raw, to_e164(raw))


def _config():
    return WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=CONTACT, service_cards=True)


async def _first_ask(config, session_id, tool_args):
    service = _service_for_responses([
        _stream_tool_call("p", "prepare_booking", tool_args),
    ])
    events = await _run(service, config, "Book Brow Lamination on 2026-10-08 at 10:30", session_id)
    return next(e for e in events if e["type"] == "done")["answer"]


def _asks(caplog):
    return [r.getMessage() for r in caplog.records if "missing_details_ask" in r.getMessage()]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,tool_args,paraphrase", [
    ("phone", '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", "full_name": "Test Demo"}',
     "I still need a phone number to go ahead, could you share it?"),
    ("name", '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", "phone": "9800000000"}',
     "I still need your name to go ahead, could you share it?"),
])
async def test_model_paraphrase_without_tool_call_reaches_handoff(caplog, kind, tool_args, paraphrase):
    caplog.set_level(logging.INFO)
    config = _config()
    sid = str(uuid.uuid4())
    reset_session_state(sid)
    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_tool_exec_side_effect):
        first = await _first_ask(config, sid, tool_args)
        assert "full name and phone number" in first
        answers = []
        for _ in range(3):
            service = _service_for_responses([_stream(paraphrase)])
            events = await _run(service, config, "mm", sid)
            answers.append(next(e for e in events if e["type"] == "done")["answer"])
    # ask 1 was the tool's; model paraphrase = ask 2 (+variant), ask 3 = handoff
    assert "one digit at a time" in answers[0] or "full name" in answers[0]
    assert CONTACT in answers[1] and "contact the clinic" in answers[1]
    # after the handoff nothing is outstanding: a further model turn is not counted
    asks = _asks(caplog)
    assert [("ask_n=%d" % n) in a for n, a in zip((1, 2, 3), asks)] == [True, True, True]
    assert "source=tool" in asks[0] and "source=model" in asks[1]
    assert "handoff=False" in asks[1] and "handoff=True" in asks[2]
    assert len(asks) == 3  # never a 4th
    reset_session_state(sid)


@pytest.mark.asyncio
@pytest.mark.parametrize("junk", ["१२३", "१२३४", "12345"])
async def test_short_phone_reply_is_gated_without_the_model(caplog, junk):
    caplog.set_level(logging.INFO)
    config = _config()
    sid = str(uuid.uuid4())
    reset_session_state(sid)
    args = '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", "full_name": "Test Demo"}'
    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_tool_exec_side_effect):
        await _first_ask(config, sid, args)
        out = []
        for _ in range(2):
            service = _service_for_responses([])  # model must NOT be called
            events = await _run(service, config, junk, sid)
            out.append(next(e for e in events if e["type"] == "done")["answer"])
            service.client.chat.completions.create.assert_not_called()
    assert ("one digit at a time" in out[0]) or ("एक-एक गरी" in out[0])  # variant, not the first ask
    assert CONTACT in out[1]
    asks = _asks(caplog)
    assert [("ask_n=%d" % n) in a for n, a in zip((1, 2, 3), asks)] == [True, True, True]
    assert "source=gate" in asks[1] and "handoff=True" in asks[2]
    reset_session_state(sid)


@pytest.mark.asyncio
async def test_valid_phone_reply_is_not_gated_and_reaches_the_model():
    config = _config()
    sid = str(uuid.uuid4())
    reset_session_state(sid)
    args = '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", "full_name": "Test Demo"}'
    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_tool_exec_side_effect):
        await _first_ask(config, sid, args)
        service = _service_for_responses([
            _stream_tool_call("p2", "prepare_booking",
                '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", '
                '"full_name": "Test Demo", "phone": "9841540434"}'),
        ])
        events = await _run(service, config, "नौ आठ चार एक पाँच चार शून्य चार तीन चार", sid)
        sent = service.client.chat.completions.create.call_args.kwargs["messages"]
    assert [m["content"] for m in sent if m["role"] == "user"][-1] == "9841540434"  # the model is handed digits
    assert next(e for e in events if e["type"] == "done").get("ui", {}).get("confirm")
    reset_session_state(sid)


@pytest.mark.asyncio
async def test_off_topic_turn_does_not_advance_the_counter(caplog):
    caplog.set_level(logging.INFO)
    config = _config()
    sid = str(uuid.uuid4())
    reset_session_state(sid)
    args = '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", "full_name": "Test Demo"}'
    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_tool_exec_side_effect):
        await _first_ask(config, sid, args)
        service = _service_for_responses([_stream("We are open 9 to 5, Sunday to Friday.")])
        await _run(service, config, "when are you open", sid)
    assert len(_asks(caplog)) == 1  # only the tool's first ask
    reset_session_state(sid)


# --- SBAL-Z10.1: gated turns never enter the conversation store ------------

def _real_store_service(responses):
    # the z8 harness stubs conversation_store out; these tests need the real one
    service = _service_for_responses(responses)
    service.conversation_store = get_conversation_store()
    return service


# Note: _TIME_SHAPED_RE's a.?m also matches the bare word "am". Harmless today
# (the name branch returns False for any turn with letters, and "I am Anis"
# has no digits) — keep in mind if the name branch is ever tightened.
@pytest.mark.parametrize("text", ["10:30", "2:30", "2.30", "2 pm", "2PM", "ek baje", "दुई बजे", "२:३०"])
def test_z101_time_shaped_turn_not_gated(text):
    from app.services.clinic_agent import _inbound_is_unusable_answer
    assert not _inbound_is_unusable_answer({"error": "INVALID_PHONE"}, text)
    assert not _inbound_is_unusable_answer({"error": "INVALID_NAME"}, text)


@pytest.mark.parametrize("text", ["१२३", "१२३४", "12345", "123"])
def test_z101_short_phone_still_gated(text):
    from app.services.clinic_agent import _inbound_is_unusable_answer
    assert _inbound_is_unusable_answer({"error": "INVALID_PHONE"}, text)


@pytest.mark.asyncio
async def test_z101_gated_turn_is_not_stored_but_assistant_ask_is():
    config = _config()
    sid = str(uuid.uuid4())
    reset_session_state(sid)
    args = '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", "full_name": "Test Demo"}'
    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_tool_exec_side_effect):
        await _run(_real_store_service([_stream_tool_call("p", "prepare_booking", args)]),
                   config, "Book Brow Lamination on 2026-10-08 at 10:30", sid)
        service = _real_store_service([])
        events = await _run(service, config, "१२३", sid)
        service.client.chat.completions.create.assert_not_called()
    answer = next(e for e in events if e["type"] == "done")["answer"]
    msgs = get_conversation_store().get_messages(sid)
    assert not [m for m in msgs if m["role"] == "user" and "१२३" in m["content"]]
    assert [m for m in msgs if m["role"] == "user" and "Brow Lamination" in m["content"]]  # control: non-gated stored
    assert [m for m in msgs if m["role"] == "assistant" and m["content"] == answer]  # the ask is kept
    reset_session_state(sid)


@pytest.mark.asyncio
async def test_z101_non_gated_turn_is_stored():
    config = _config()
    sid = str(uuid.uuid4())
    reset_session_state(sid)
    args = '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", "full_name": "Test Demo"}'
    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_tool_exec_side_effect):
        await _run(_real_store_service([_stream_tool_call("p", "prepare_booking", args)]),
                   config, "Book Brow Lamination on 2026-10-08 at 10:30", sid)
        await _run(_real_store_service([_stream("We are open 9 to 5.")]), config, "when are you open", sid)
    msgs = get_conversation_store().get_messages(sid)
    assert [m for m in msgs if m["role"] == "user" and m["content"] == "when are you open"]
    reset_session_state(sid)
