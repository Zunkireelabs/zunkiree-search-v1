"""
CLINIC-BOOKING-TRUTH-BRIEF F1: the agent must never state or imply a booking
was made unless confirm_booking actually returned a booking_number in that
same turn. A live run showed the model narrating "मैले ... बुक गरेको छु"
("I have booked") on a turn where confirm_booking was never called — the
guard held (nothing was actually written), but the SPEECH was false. Fixed
by never letting the model compose the wrap-up text in that situation: the
reply is built deterministically from prepare_booking's own summary and the
turn ends immediately, so the model is never given a chance to generate a
false claim.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import ClinicAgentService


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000ee"),
        name="Dental City",
        site_id="dental-city",
        api_key="key",
        website_type="clinic",
    )


def _chunk(content=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None))])


async def _stream(text: str):
    yield _chunk(content=text)


def _tool_call_chunk(call_id: str, name: str, arguments: str):
    delta = SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(index=0, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))],
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


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


async def _run(service: ClinicAgentService, config, question: str, session_id: str = "s1", channel: str = "chat"):
    customer = _make_customer()
    events = []
    async for event in service.process_agent_stream(
        db=AsyncMock(),
        site_id="dental-city",
        session_id=session_id,
        question=question,
        customer_id=customer.id,
        customer=customer,
        config=config,
        brand_name="Dental City",
        channel=channel,
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_prepare_without_confirm_never_claims_booked():
    """Reproduces NE-4 T3: prepare_booking succeeds, confirm_booking is
    never called this turn. Even though the model's OWN generated text
    would have said "I have booked", the model is never asked — the reply
    must be the deterministic read-back + question, and must not claim a
    booking exists."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)

    # Only ONE response is provided: the prepare_booking tool call. If the
    # code asked the model to narrate a wrap-up (the bug), it would try to
    # pop a second response and fail with IndexError — proving the model
    # was never called again.
    responses = [
        _stream_tool_call(
            "call_1", "prepare_booking",
            '{"service": "General Dentistry", "date": "2026-09-20", "time": "12:00", '
            '"full_name": "Test Patient", "phone": "9841234567"}',
        ),
    ]
    service = _service_for_responses(responses)

    fake_result = {
        "summary": "General Dentistry on Sunday, 2026-09-20 at 12:00 for Test Patient (+9779841234567) at Main Branch.",
        "pending_booking": {
            "service_name": "General Dentistry", "date": "2026-09-20", "time": "12:00",
            "full_name": "Test Patient", "phone_e164": "+9779841234567", "branch_name": "Main Branch",
        },
    }
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=fake_result)):
        events = await _run(service, config, question="हुन्छ, गर्दिनुस्।")

    done_event = next(e for e in events if e["type"] == "done")
    answer = done_event["answer"]

    assert "बुक गरेको छु" not in answer  # "I have booked" — the false claim
    assert "I have booked" not in answer
    assert "General Dentistry" in answer
    assert "2026-09-20" in answer
    assert answer.strip().endswith("?")  # ends in the confirmation question


@pytest.mark.asyncio
async def test_prepare_without_confirm_uses_localized_question_for_devanagari():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    responses = [
        _stream_tool_call(
            "call_1", "prepare_booking",
            '{"service": "Teeth Cleaning", "date": "2026-09-19", "time": "10:00", '
            '"full_name": "Test Patient", "phone": "9841234567"}',
        ),
    ]
    service = _service_for_responses(responses)
    fake_result = {
        "summary": "Teeth Cleaning on Saturday, 2026-09-19 at 10:00 for Test Patient (+9779841234567) at Main Branch.",
        "pending_booking": {},
    }
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=fake_result)):
        events = await _run(service, config, question="भोलि दाँत सफा गर्न मिल्छ?")

    done_event = next(e for e in events if e["type"] == "done")
    assert "के म यसलाई बुक गरौं?" in done_event["answer"]


@pytest.mark.asyncio
async def test_failed_prepare_does_not_trigger_override():
    """A FAILED prepare_booking (e.g. unknown service name) must not set
    turn_prepared_summary — the model's own (normal) response to the error
    passes through untouched."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    responses = [
        _stream_tool_call(
            "call_1", "prepare_booking",
            '{"service": "Teeth Cleaning", "date": "2026-09-20", "time": "12:00", '
            '"full_name": "Test Patient", "phone": "9841234567"}',
        ),
        _stream("I couldn't find that service — did you mean General Dentistry?"),
    ]
    service = _service_for_responses(responses)
    fake_result = {"error": "SERVICE_NOT_FOUND", "message": "Couldn't find a service matching 'Teeth Cleaning'."}
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=fake_result)):
        events = await _run(service, config, question="Teeth cleaning please, 12pm")

    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["answer"] == "I couldn't find that service — did you mean General Dentistry?"


@pytest.mark.asyncio
async def test_successful_confirm_lets_models_own_answer_through():
    """When confirm_booking actually returns a booking_number this turn,
    the override must NOT fire — the model's own (true) claim passes
    through normally."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    responses = [
        _stream_tool_call("call_1", "confirm_booking", "{}"),
        _stream("Your booking is confirmed — reference BK-20260921-0001."),
    ]
    service = _service_for_responses(responses)
    fake_result = {
        "booking": {
            "booking_number": "BK-20260921-0001",
            "date": "2026-09-21", "start_time": "10:00",
            "treatment_name": "General Dentistry", "branch_name": "Main Branch",
        }
    }
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=fake_result)):
        events = await _run(service, config, question="Yes, please confirm.")

    done_event = next(e for e in events if e["type"] == "done")
    assert "BK-20260921-0001" in done_event["answer"]


@pytest.mark.asyncio
async def test_confirm_blocked_same_turn_still_gets_deterministic_readback():
    """If the model prepares AND tries to confirm in the same turn (the
    same-turn guard blocks the confirm), the reply must still be the
    deterministic read-back/question — not whatever the model says about
    the blocked confirm attempt."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)

    def _multi_tool_call_stream():
        delta = SimpleNamespace(
            content=None,
            tool_calls=[
                SimpleNamespace(
                    index=0, id="call_1",
                    function=SimpleNamespace(
                        name="prepare_booking",
                        arguments='{"service": "General Dentistry", "date": "2026-09-20", "time": "12:00", '
                                  '"full_name": "Test Patient", "phone": "9841234567"}',
                    ),
                ),
                SimpleNamespace(
                    index=1, id="call_2",
                    function=SimpleNamespace(name="confirm_booking", arguments="{}"),
                ),
            ],
        )
        return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    async def _stream_both():
        yield _multi_tool_call_stream()

    responses = [_stream_both()]
    service = _service_for_responses(responses)

    prepare_result = {
        "summary": "General Dentistry on Sunday, 2026-09-20 at 12:00 for Test Patient (+9779841234567) at Main Branch.",
        "pending_booking": {},
    }
    confirm_result = {"error": "NEEDS_CONFIRMATION", "message": "wait for explicit yes"}

    async def fake_execute(tool_name, **kwargs):
        return prepare_result if tool_name == "prepare_booking" else confirm_result

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(side_effect=fake_execute)):
        events = await _run(service, config, question="Book General Dentistry Sunday at noon and confirm it.")

    done_event = next(e for e in events if e["type"] == "done")
    answer = done_event["answer"]
    assert "General Dentistry" in answer
    assert answer.strip().endswith("?")
