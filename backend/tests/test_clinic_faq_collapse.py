"""
P4 Wave 2 B4: collapse the knowledge/FAQ round trip from 2 LLM completions to
1. Today a plain FAQ costs iteration 1 (decide to call search_knowledge) +
iteration 2 (answer from the result). This runs retrieval BEFORE the loop for
turns a cheap classifier is confident are knowledge-only, injects the result
into the system prompt, and withholds search_knowledge (only) from the first
iteration's tool list so the model can't redundantly call it again.

Booking, availability, prepare/confirm must keep their full tool loop
unchanged — the classifier is deliberately conservative (see
_is_knowledge_only_turn in clinic_agent.py): every tool other than
search_knowledge stays available on the fast-pathed iteration, so a
misclassified turn still reaches the correct tool exactly as before.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services import clinic_tools
from app.services.clinic_agent import ClinicAgentService, _is_knowledge_only_turn, reset_date_anchor
from datetime import datetime
from app.services.clinic_agent import NPT


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000ee"),
        name="Dental City",
        site_id="dental-city",
        api_key="key",
        website_type="clinic",
    )


@pytest.fixture(autouse=True)
def _reset_state():
    clinic_tools.reset_quick_facts_cache()
    clinic_tools.reset_org_cache()
    yield
    clinic_tools.reset_quick_facts_cache()
    clinic_tools.reset_org_cache()


def _chunk(content=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None))])


def _tool_call_chunk(call_id: str, name: str, arguments: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(index=0, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))],
        ))]
    )


async def _stream(text: str):
    yield _chunk(content=text)


async def _stream_tool_call(call_id: str, name: str, arguments: str):
    yield _tool_call_chunk(call_id, name, arguments)


def _service_for_responses(responses: list) -> ClinicAgentService:
    service = ClinicAgentService()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=lambda **kw: responses.pop(0))
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


async def _run(service, config, question, session_id, db=None):
    customer = _make_customer()
    events = []
    async for event in service.process_agent_stream(
        db=db if db is not None else AsyncMock(),
        site_id="dental-city",
        session_id=session_id,
        question=question,
        customer_id=customer.id,
        customer=customer,
        config=config,
        brand_name="Dental City",
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_faq_question_costs_a_single_llm_call():
    """The knowledge fast path: one completion, not two, for a plain FAQ."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    service = _service_for_responses([_stream("We're open 10 AM to 8 PM every day.")])

    with patch(
        "app.services.clinic_agent.execute_clinic_tool",
        AsyncMock(return_value={"chunks": [{"content": "Hours: 10 AM - 8 PM daily."}]}),
    ) as mock_tool:
        events = await _run(service, config, "What are your opening hours?", session_id="faq-1")

    assert service.client.chat.completions.create.await_count == 1
    done_event = next(e for e in events if e["type"] == "done")
    assert "open" in done_event["answer"].lower()
    # The prefetch is the ONLY execute_clinic_tool call this turn — no
    # second, redundant search_knowledge call from the model.
    assert mock_tool.await_count == 1
    assert mock_tool.await_args.kwargs["tool_name"] == "search_knowledge"


@pytest.mark.asyncio
async def test_faq_prompt_carries_prefetched_knowledge_and_drops_the_tool():
    """The system prompt gets the retrieved facts injected, and the first
    completion call's tool list omits search_knowledge (everything else
    stays available)."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    captured_calls: list = []

    def _create(**kw):
        captured_calls.append(kw)
        return _stream("We're open 10 AM to 8 PM.")

    service = ClinicAgentService()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None

    with patch(
        "app.services.clinic_agent.execute_clinic_tool",
        AsyncMock(return_value={"chunks": [{"content": "Hours: 10 AM - 8 PM daily."}]}),
    ):
        await _run(service, config, "What are your opening hours?", session_id="faq-2")

    system_prompt = captured_calls[0]["messages"][0]["content"]
    assert "KNOWLEDGE-THIS-TURN" in system_prompt
    assert "Hours: 10 AM - 8 PM daily." in system_prompt
    tool_names = {t["function"]["name"] for t in captured_calls[0]["tools"]}
    assert "search_knowledge" not in tool_names
    assert {"list_services", "check_availability", "prepare_booking", "confirm_booking"} <= tool_names


@pytest.mark.asyncio
async def test_booking_turn_keeps_the_full_two_call_tool_loop():
    """A booking-shaped turn must NOT be fast-pathed — same iteration count
    and same tools as before this brief."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    service = _service_for_responses([
        _stream_tool_call("call_1", "check_availability", '{"service": "General Dentistry"}'),
        _stream("We have a slot tomorrow at 10 AM."),
    ])

    with patch(
        "app.services.clinic_agent.execute_clinic_tool",
        AsyncMock(return_value={"service": {"name": "General Dentistry"}, "open_times": []}),
    ) as mock_tool:
        events = await _run(
            service, config, "I'd like to book a General Dentistry appointment", session_id="booking-1"
        )

    assert service.client.chat.completions.create.await_count == 2
    assert mock_tool.await_count == 1
    assert mock_tool.await_args.kwargs["tool_name"] == "check_availability"
    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["answer"]


@pytest.mark.asyncio
async def test_escalation_question_is_not_fast_pathed():
    """Medical-escalation-shaped turns keep the unchanged tool-decision loop
    (the classifier excludes them outright, regardless of channel)."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone="980-1222339")
    service = _service_for_responses([
        _stream_tool_call("call_1", "search_knowledge", '{"query": "emergency"}'),
        _stream("Please call the clinic immediately at 980-1222339."),
    ])

    with patch(
        "app.services.clinic_agent.execute_clinic_tool",
        AsyncMock(return_value={"chunks": []}),
    ):
        await _run(
            service, config, "My tooth is badly swollen and bleeding, help!", session_id="escalation-1"
        )

    assert service.client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_mid_booking_followup_is_not_fast_pathed():
    """A session with a live date anchor from an earlier booking turn must
    not fast-path a bare follow-up that names no booking keyword at all."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    session_id = "midbooking-1"
    reset_date_anchor(session_id)

    with patch(
        "app.services.clinic_agent.execute_clinic_tool",
        AsyncMock(return_value={"service": {"name": "General Dentistry"}, "open_times": []}),
    ):
        # Turn 1: names a relative date + service — anchors the session.
        service1 = _service_for_responses([
            _stream_tool_call("call_1", "check_availability", '{"service": "General Dentistry"}'),
            _stream("Tomorrow has an opening at 10 AM."),
        ])
        await _run(service1, config, "book me a cleaning tomorrow", session_id=session_id)

        # Turn 2: no booking keyword, no date word — must still avoid the
        # fast path because the session is mid-booking.
        service2 = _service_for_responses([
            _stream_tool_call("call_2", "check_availability", '{"service": "General Dentistry"}'),
            _stream("That works, want me to hold it?"),
        ])
        await _run(service2, config, "what about 3pm instead", session_id=session_id)

    assert service2.client.chat.completions.create.await_count == 2
    reset_date_anchor(session_id)


def test_classifier_excludes_pricing_and_availability_wording():
    now = datetime.now(NPT)
    assert _is_knowledge_only_turn("What are your opening hours?", now) is True
    assert _is_knowledge_only_turn("Where is the clinic located?", now) is True
    assert _is_knowledge_only_turn("How much does a cleaning cost?", now) is False
    assert _is_knowledge_only_turn("Do you have any slots available?", now) is False
    assert _is_knowledge_only_turn("I want to book an appointment", now) is False
    assert _is_knowledge_only_turn("My gum is bleeding a lot", now) is False
    assert _is_knowledge_only_turn("यो भोलि खाली छ?", now) is False
    assert _is_knowledge_only_turn("ok", now) is False
