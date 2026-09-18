"""
CLINIC-BOOKING-FLOW-VOICE-BRIEF D1: within one conversation about a single
day (पर्सी), the live session queried three different dates across turns
because the LLM was resolving भोलि/पर्सी itself, turn by turn, with no
persistence. This must be resolved deterministically against clinic-local
time and anchored in session state, not left to the model's own arithmetic
(same llm_prompt_mandate_vs_actual_behavior pattern as IG-9/IG-5).
"""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import (
    ClinicAgentService,
    NPT,
    _resolve_relative_date_word,
    _EXPLICIT_DATE_SIGNAL,
    _DATE_ANCHOR,
    reset_date_anchor,
)


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000dd"),
        name="Dental City",
        site_id="dental-city",
        api_key="key",
        website_type="clinic",
    )


@pytest.fixture(autouse=True)
def _reset_anchor():
    reset_date_anchor("s1")
    yield
    reset_date_anchor("s1")


# --- Unit: deterministic word resolution ---

def _today_plus(days: int) -> str:
    return (datetime.now(NPT).date() + timedelta(days=days)).isoformat()


@pytest.mark.parametrize(
    "text,offset",
    [
        ("भोलि कति बजे खाली छ?", 1),
        ("पर्सी बुक गर्न मिल्छ?", 2),
        ("आज खाली समय छ?", 0),
        ("bholi available time?", 1),
        ("parsi is fine for me", 2),
        ("is there anything available tomorrow?", 1),
        ("what about day after tomorrow?", 2),
        ("do you have anything today?", 0),
    ],
)
def test_resolve_relative_date_word(text, offset):
    now_npt = datetime.now(NPT)
    assert _resolve_relative_date_word(text, now_npt) == _today_plus(offset)


def test_resolve_relative_date_word_returns_none_for_unrelated_text():
    now_npt = datetime.now(NPT)
    assert _resolve_relative_date_word("सात बजेको गर्दिनोस्", now_npt) is None
    assert _resolve_relative_date_word("", now_npt) is None


@pytest.mark.parametrize(
    "text",
    [
        "आजकल दाँत दुखिरहेको छ",  # "lately" — not "today"
        "आजभोलि दाँत दुख्छ",  # "nowadays" — not "today" or "tomorrow"
    ],
)
def test_resolve_relative_date_word_ignores_aajkal_aajabholi_false_positive(text):
    """PR #64 review MUST 2b: आज has no reliable word boundary against
    Devanagari, so it was matching inside आजकल ('lately') and आजभोलि
    ('nowadays') — both common in symptom descriptions and neither meaning
    'today'. भोलि must also not fire inside आजभोलि."""
    now_npt = datetime.now(NPT)
    assert _resolve_relative_date_word(text, now_npt) is None


# --- MUST 2a: weekday / next-week phrases must be treated as explicit,   ---
# --- never silently overridden by a stale anchor from an earlier turn.   ---

@pytest.mark.parametrize(
    "text",
    [
        "सोमबार को मिल्छ?",
        "मंगलबार खाली छ?",
        "अर्को हप्ता आउँछु",
        "next Monday works for me",
        "how about this Friday?",
        "is Monday available?",
    ],
)
def test_weekday_and_next_week_phrases_are_explicit_date_signals(text):
    assert _EXPLICIT_DATE_SIGNAL.search(text) is not None


# --- Integration: the tool call actually executed gets the resolved date ---

def _tool_call_chunk(call_id: str, name: str, arguments: str):
    delta = SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(index=0, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))],
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


async def _stream_tool_call(call_id: str, name: str, arguments: str):
    yield _tool_call_chunk(call_id, name, arguments)


def _chunk(content=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None))])


async def _stream(text: str):
    yield _chunk(content=text)


def _service_for_tool_sequence(responses: list):
    service = ClinicAgentService()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=lambda **kw: responses.pop(0))
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


@pytest.mark.asyncio
async def test_check_availability_date_is_overridden_to_resolved_parsi_date():
    """Reproduces the live-session defect: the model asks about पर्सी but
    passes a wrong date to check_availability (like the 2026-09-22 in the
    transcript instead of the correct +2 day). The date actually EXECUTED
    must be the deterministically-resolved one, not the model's guess."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    customer = _make_customer()

    wrong_date = _today_plus(4)  # what the model incorrectly passed in the transcript
    correct_date = _today_plus(2)  # पर्सी = day after tomorrow

    responses = [
        _stream_tool_call("call_1", "check_availability", f'{{"service": "General Dentistry", "date": "{wrong_date}"}}'),
        _stream("भोलिको लागि केही समय उपलब्ध छ।"),
    ]
    service = _service_for_tool_sequence(responses)

    captured_calls = []

    async def fake_execute(**kwargs):
        captured_calls.append(kwargs)
        return {"service": {"name": "General Dentistry"}, "date": kwargs["tool_args"].get("date"), "open_times": []}

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(side_effect=fake_execute)):
        events = []
        async for event in service.process_agent_stream(
            db=AsyncMock(),
            site_id="dental-city",
            session_id="s1",
            question="पर्सी बुक गर्न मिल्छ?",
            customer_id=customer.id,
            customer=customer,
            config=config,
            brand_name="Dental City",
        ):
            events.append(event)

    assert len(captured_calls) == 1
    assert captured_calls[0]["tool_args"]["date"] == correct_date
    assert captured_calls[0]["tool_args"]["date"] != wrong_date


@pytest.mark.asyncio
async def test_anchored_date_persists_to_a_follow_up_turn_naming_only_a_time():
    """Turn N resolves पर्सी. Turn N+1 names only a time ("सात बजेको
    गर्दिनोस्", no date word at all) — the anchor from turn N must still be
    the date used, not whatever the model comes up with on its own."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    customer = _make_customer()
    correct_date = _today_plus(2)

    captured_calls = []

    async def fake_execute(**kwargs):
        captured_calls.append(kwargs)
        return {"service": {"name": "General Dentistry"}, "date": kwargs["tool_args"].get("date"), "open_times": []}

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(side_effect=fake_execute)):
        # Turn 1: पर्सी.
        service1 = _service_for_tool_sequence([
            _stream_tool_call("call_1", "check_availability", '{"service": "General Dentistry"}'),
            _stream("भोलिको लागि केही समय उपलब्ध छ।"),
        ])
        async for _ in service1.process_agent_stream(
            db=AsyncMock(), site_id="dental-city", session_id="s1",
            question="पर्सी बुक गर्न मिल्छ?", customer_id=customer.id, customer=customer,
            config=config, brand_name="Dental City",
        ):
            pass

        # Turn 2: only a time, no date word — should still use the anchor.
        service2 = _service_for_tool_sequence([
            _stream_tool_call("call_2", "check_availability", '{"service": "General Dentistry", "date": "2099-01-01"}'),
            _stream("सात बजे उपलब्ध छैन।"),
        ])
        async for _ in service2.process_agent_stream(
            db=AsyncMock(), site_id="dental-city", session_id="s1",
            question="सात बजेको गर्दिनोस्", customer_id=customer.id, customer=customer,
            config=config, brand_name="Dental City",
        ):
            pass

    assert len(captured_calls) == 2
    assert captured_calls[0]["tool_args"]["date"] == correct_date
    assert captured_calls[1]["tool_args"]["date"] == correct_date


@pytest.mark.asyncio
async def test_explicit_absolute_date_this_turn_is_not_overridden_by_stale_anchor():
    """If the visitor names an explicit absolute date (गते-style), a stale
    anchor from an earlier turn must not clobber it."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    customer = _make_customer()

    _DATE_ANCHOR["s1"] = _today_plus(2)  # stale anchor from an earlier turn

    captured_calls = []

    async def fake_execute(**kwargs):
        captured_calls.append(kwargs)
        return {"service": {"name": "General Dentistry"}, "date": kwargs["tool_args"].get("date"), "open_times": []}

    responses = [
        _stream_tool_call("call_1", "check_availability", '{"service": "General Dentistry", "date": "2026-10-25"}'),
        _stream("२५ गतेको लागि समय उपलब्ध छ।"),
    ]
    service = _service_for_tool_sequence(responses)

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(side_effect=fake_execute)):
        async for _ in service.process_agent_stream(
            db=AsyncMock(), site_id="dental-city", session_id="s1",
            question="२५ गते के खाली छ?", customer_id=customer.id, customer=customer,
            config=config, brand_name="Dental City",
        ):
            pass

    assert captured_calls[0]["tool_args"]["date"] == "2026-10-25"


@pytest.mark.asyncio
async def test_next_monday_this_turn_is_not_overridden_by_stale_bholi_anchor():
    """PR #64 review MUST 2a: an earlier भोलि anchor must not clobber a
    later turn that names a weekday/next-week phrase — previously "next
    Monday" fell through to neither the relative NOR the explicit signal
    and got silently overridden to the stale anchored date."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    customer = _make_customer()

    _DATE_ANCHOR["s1"] = _today_plus(1)  # stale "भोलि" anchor from an earlier turn

    captured_calls = []

    async def fake_execute(**kwargs):
        captured_calls.append(kwargs)
        return {"service": {"name": "General Dentistry"}, "date": kwargs["tool_args"].get("date"), "open_times": []}

    responses = [
        _stream_tool_call("call_1", "check_availability", '{"service": "General Dentistry", "date": "2026-10-19"}'),
        _stream("Next Monday works, here are the open times."),
    ]
    service = _service_for_tool_sequence(responses)

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(side_effect=fake_execute)):
        async for _ in service.process_agent_stream(
            db=AsyncMock(), site_id="dental-city", session_id="s1",
            question="Does next Monday work instead?", customer_id=customer.id, customer=customer,
            config=config, brand_name="Dental City",
        ):
            pass

    assert captured_calls[0]["tool_args"]["date"] == "2026-10-19"


@pytest.mark.asyncio
async def test_sessionless_turn_does_not_leak_anchor_across_visitors():
    """MINOR (PR #64 review): sessions without an id must not share one
    global anchor — otherwise visitor A's resolved date leaks into visitor
    B's tool calls. A relative word still resolves and enforces for that
    single turn; it just isn't persisted to or read from shared state."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    customer = _make_customer()
    correct_date = _today_plus(1)

    captured_calls = []

    async def fake_execute(**kwargs):
        captured_calls.append(kwargs)
        return {"service": {"name": "General Dentistry"}, "date": kwargs["tool_args"].get("date"), "open_times": []}

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(side_effect=fake_execute)):
        # Visitor A, no session_id, says भोलि.
        service_a = _service_for_tool_sequence([
            _stream_tool_call("call_1", "check_availability", '{"service": "General Dentistry"}'),
            _stream("भोलिको लागि समय उपलब्ध छ।"),
        ])
        async for _ in service_a.process_agent_stream(
            db=AsyncMock(), site_id="dental-city", session_id="",
            question="भोलि खाली छ?", customer_id=customer.id, customer=customer,
            config=config, brand_name="Dental City",
        ):
            pass

        # Visitor B, also no session_id, names only a time — must NOT
        # inherit visitor A's anchored भोलि date.
        service_b = _service_for_tool_sequence([
            _stream_tool_call("call_2", "check_availability", '{"service": "General Dentistry", "date": "2099-01-01"}'),
            _stream("त्यो समय उपलब्ध छैन।"),
        ])
        async for _ in service_b.process_agent_stream(
            db=AsyncMock(), site_id="dental-city", session_id="",
            question="सात बजेको गर्दिनोस्", customer_id=customer.id, customer=customer,
            config=config, brand_name="Dental City",
        ):
            pass

    assert captured_calls[0]["tool_args"]["date"] == correct_date
    # Visitor B got no anchor to inherit, so their own tool-call date (which
    # the model supplied) passes through unmodified rather than being
    # overridden with visitor A's भोलि date.
    assert captured_calls[1]["tool_args"]["date"] == "2099-01-01"
