"""SBAL-Z14: F15 turn ownership, F16 terminal handoff, F17 per-detail ask
budget + mid-booking flow-turn budget. Everything is scored on structure
(did a tool get called), never on the model's wording."""
import asyncio
import logging
import uuid
from unittest.mock import patch

import pytest

from app.models.widget_config import WidgetConfig
from app.services import clinic_agent
from app.services.clinic_tools import (
    bump_flow_turns, bump_missing_asks, is_handed_off, reset_session_state,
)
from tests.test_clinic_booking_flow_language_sbal_z8 import (
    _run, _service_for_responses, _stream, _stream_tool_call, _tool_exec_side_effect,
)

CONTACT = "01-4444444"
PHONE_MISSING_ARGS = '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", "full_name": "Test Demo"}'
NAME_MISSING_ARGS = '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", "phone": "9800000000"}'
PARAPHRASE = "I didn't catch that; could you rephrase?"  # the failure-1 shape: no keyword


def _config():
    return WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=CONTACT, service_cards=True)


def _exec(**kwargs):
    if kwargs["tool_name"] == "search_knowledge":
        return {"chunks": [{"content": "We are open 9 to 5, Sunday to Friday."}]}
    return _tool_exec_side_effect(**kwargs)


def _answer(events):
    return next(e for e in events if e["type"] == "done")["answer"]


def _tokens(events):
    return "".join(e["data"] for e in events if e["type"] == "token")


def _asks(caplog):
    return [r.getMessage() for r in caplog.records if "missing_details_ask" in r.getMessage()]


def _flow(caplog):
    return [r.getMessage() for r in caplog.records if "booking_flow" in r.getMessage()]


async def _arm(config, sid, tool_args=PHONE_MISSING_ARGS):
    """Turn 1: prepare_booking fails on the visitor's own detail (ask 1, ours)."""
    service = _service_for_responses([_stream_tool_call("p", "prepare_booking", tool_args)])
    return _answer(await _run(service, config, "Book Brow Lamination on 2026-10-08 at 10:30", sid))


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_args,kind", [(PHONE_MISSING_ARGS, "phone"), (NAME_MISSING_ARGS, "name")])
async def test_f15_text_only_turn_is_discarded_counted_and_reaches_handoff(caplog, tool_args, kind):
    caplog.set_level(logging.INFO)
    config, sid = _config(), str(uuid.uuid4())
    reset_session_state(sid)
    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_exec):
        await _arm(config, sid, tool_args)
        out, toks = [], []
        for _ in range(2):
            events = await _run(_service_for_responses([_stream(PARAPHRASE)]), config, "mm", sid)
            out.append(_answer(events))
            toks.append(_tokens(events))
    # the caller never hears the model's paraphrase — the reply is ours, one request only
    assert all("rephrase" not in t and "rephrase" not in a for t, a in zip(toks, out))
    assert out[0].count("?") == 0 and "full name and phone" not in out[0]  # variant, not a stacked ask
    assert CONTACT in out[1] and "contact the clinic" in out[1]  # ask 3 = handoff
    asks = _asks(caplog)
    assert len(asks) == 3 and "source=tool" in asks[0]
    assert "source=owned" in asks[1] and "source=owned" in asks[2] and "handoff=True" in asks[2]
    assert is_handed_off(sid)
    reset_session_state(sid)


@pytest.mark.asyncio
async def test_f16_handoff_is_terminal_for_booking_turns_and_never_a_fourth_ask(caplog):
    """After the handoff a structurally-booking turn (a gated answer, or a
    failing booking tool) is acknowledged, never re-asked."""
    caplog.set_level(logging.INFO)
    config, sid = _config(), str(uuid.uuid4())
    reset_session_state(sid)
    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_exec):
        await _arm(config, sid)
        for _ in range(2):
            await _run(_service_for_responses([_stream(PARAPHRASE)]), config, "mm", sid)
        assert is_handed_off(sid)
        gated = _answer(await _run(_service_for_responses([_stream("x")]), config, "123", sid))
        tool = _answer(await _run(_service_for_responses([
            _stream_tool_call("p", "prepare_booking", PHONE_MISSING_ARGS),
        ]), config, "try again", sid))
    assert all(CONTACT not in a and "phone number" not in a for a in (gated, tool))
    assert len(_asks(caplog)) == 3  # never a 4th
    reset_session_state(sid)


@pytest.mark.asyncio
@pytest.mark.parametrize("channel,abandon_prefetch", [("instagram", False), ("voice", False), ("voice", True)])
async def test_f16a_post_handoff_faq_is_answered_not_muted(caplog, channel, abandon_prefetch):
    caplog.set_level(logging.INFO)
    """Exit test 3: a post-handoff FAQ gets the model's answer — including on
    voice with an ABANDONED prefetch (turn_tool_called stays False there, the
    case that used to collapse into 'Okay. Let me know...')."""
    config, sid = _config(), str(uuid.uuid4())
    reset_session_state(sid)
    state = {"slow": False}

    async def exec_(**kw):
        if state["slow"] and kw["tool_name"] == "search_knowledge":
            await asyncio.sleep(10)
        return _exec(**kw)

    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=exec_):
        await _arm(config, sid)
        for _ in range(2):
            await _run(_service_for_responses([_stream(PARAPHRASE)]), config, "mm", sid)
        assert is_handed_off(sid)
        clinic_agent._DATE_ANCHOR.pop(sid, None)  # an FAQ turn takes the prefetch lane
        state["slow"] = abandon_prefetch
        with patch.object(clinic_agent, "VOICE_KNOWLEDGE_PREFETCH_TIMEOUT_S", 0.05):
            events = await _run(
                _service_for_responses([_stream("We are open 9 to 5, Sunday to Friday.")]),
                config, "what are your opening hours", sid, channel=channel,
            )
    assert _answer(events) == "We are open 9 to 5, Sunday to Friday."
    assert "Let me know if there's anything else" not in _answer(events)
    assert ("knowledge_prefetch_abandoned" in caplog.text) == abandon_prefetch  # the scenario really ran
    reset_session_state(sid)


@pytest.mark.asyncio
async def test_f15_tool_call_is_progress_nothing_counted(caplog):
    """The test-B shape: the model checks availability and asks for the phone."""
    caplog.set_level(logging.INFO)
    config, sid = _config(), str(uuid.uuid4())
    reset_session_state(sid)
    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_exec):
        await _arm(config, sid)
        events = await _run(_service_for_responses([
            _stream_tool_call("c", "check_availability", '{"service": "Brow Lamination", "date": "2026-10-08"}'),
            _stream("I can book you at 10:30 — may I have your phone number?"),
        ]), config, "10:30", sid)
    assert _answer(events) == "I can book you at 10:30 — may I have your phone number?"
    assert len(_asks(caplog)) == 1 and not is_handed_off(sid)
    reset_session_state(sid)


def test_f17_ask_budget_is_per_detail():
    sid = str(uuid.uuid4())
    reset_session_state(sid)
    assert bump_missing_asks(sid, repeat=False, kind="phone") == 1
    assert bump_missing_asks(sid, repeat=True, kind="phone") == 2
    assert bump_missing_asks(sid, repeat=True, kind="phone") == 3
    # the name is a fresh detail: it gets its own ask -> variant -> handoff run
    assert bump_missing_asks(sid, repeat=False, kind="name") == 1
    assert bump_missing_asks(sid, repeat=True, kind="name") == 2
    reset_session_state(sid)


def test_f17_per_detail_first_ask_of_a_new_detail_is_attempt_one_even_when_flagged_repeat():
    """The off-by-one: the second detail must get ask 1 -> variant 2 -> handoff 3."""
    sid = str(uuid.uuid4())
    reset_session_state(sid)
    for _ in range(3):
        bump_missing_asks(sid, repeat=True, kind="phone")
    assert [bump_missing_asks(sid, repeat=True, kind="name") for _ in range(3)] == [1, 2, 3]
    reset_session_state(sid)


@pytest.mark.asyncio
async def test_f17_stuck_turn_budget_hands_off_without_calling_the_model(caplog):
    caplog.set_level(logging.INFO)
    config, sid = _config(), str(uuid.uuid4())
    reset_session_state(sid)
    clinic_agent._DATE_ANCHOR[sid] = "2026-10-08"  # mid_booking_flow, the existing signal
    try:
        for _ in range(clinic_agent.BOOKING_FLOW_MAX_TURNS):
            bump_flow_turns(sid)  # six STUCK turns already
        service = _service_for_responses([])  # the model must NOT be called
        events = await _run(service, config, "hmm", sid)
        service.client.chat.completions.create.assert_not_called()
        assert CONTACT in _answer(events)
        assert is_handed_off(sid)
        assert any("state=budget_exhausted" in m for m in _flow(caplog))
    finally:
        clinic_agent._DATE_ANCHOR.pop(sid, None)
        reset_session_state(sid)


@pytest.mark.asyncio
async def test_f17_does_not_fire_inside_the_budget_or_without_an_anchor(caplog):
    caplog.set_level(logging.INFO)
    config, sid = _config(), str(uuid.uuid4())
    reset_session_state(sid)
    for _ in range(clinic_agent.BOOKING_FLOW_MAX_TURNS + 2):
        bump_flow_turns(sid)  # budget spent, but no live date anchor -> not mid_booking_flow
    events = await _run(_service_for_responses([_stream("Hello!")]), config, "hi", sid)
    assert _answer(events) == "Hello!" and not is_handed_off(sid)
    reset_session_state(sid)


@pytest.mark.asyncio
async def test_f17_a_long_successful_booking_is_never_handed_off(caplog):
    """The blocker: BOOKING_FLOW_MAX_TURNS counts STUCK turns. A healthy
    booking (a tool call every turn) well past the cap must not hand off."""
    caplog.set_level(logging.INFO)
    config, sid = _config(), str(uuid.uuid4())
    reset_session_state(sid)
    clinic_agent._DATE_ANCHOR[sid] = "2026-10-08"
    turns = clinic_agent.BOOKING_FLOW_MAX_TURNS + 3
    try:
        with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_exec):
            for i in range(turns):
                service = _service_for_responses([
                    _stream_tool_call(f"k{i}", "search_knowledge", '{"query": "x"}'),
                    _stream(f"step {i}"),
                ])
                events = await _run(service, config, f"turn {i}", sid)
                assert _answer(events) == f"step {i}"
                assert not is_handed_off(sid)
        assert not any("state=budget_exhausted" in m for m in _flow(caplog))
    finally:
        clinic_agent._DATE_ANCHOR.pop(sid, None)
        reset_session_state(sid)


@pytest.mark.asyncio
async def test_f17_consecutive_stuck_turns_do_hand_off(caplog):
    """Text-only mid-booking turns (no tool, no outstanding detail) ARE stuck."""
    caplog.set_level(logging.INFO)
    config, sid = _config(), str(uuid.uuid4())
    reset_session_state(sid)
    clinic_agent._DATE_ANCHOR[sid] = "2026-10-08"
    try:
        for i in range(clinic_agent.BOOKING_FLOW_MAX_TURNS):
            events = await _run(_service_for_responses([_stream(f"hm {i}")]), config, "hmm", sid)
            assert _answer(events) == f"hm {i}"
        service = _service_for_responses([])
        events = await _run(service, config, "hmm", sid)
        service.client.chat.completions.create.assert_not_called()
        assert is_handed_off(sid) and CONTACT in _answer(events)
    finally:
        clinic_agent._DATE_ANCHOR.pop(sid, None)
        reset_session_state(sid)
