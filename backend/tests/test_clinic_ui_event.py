"""
SBAL-Z2 item 2: the clinic agent's `done` event gains an optional, structured
`ui` object built from tool results, never model text — services/slots/
confirm/booking. Voice and chat ignore the extra key (no behaviour change);
only the IG adapter (chatbot_webhooks.py) renders it.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.widget_config import WidgetConfig
from app.models.customer import Customer
from app.services.clinic_agent import ClinicAgentService, _booking_ui, _services_ui, _slots_ui


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000ff"),
        name="SBAL",
        site_id="sbal",
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


async def _run(service: ClinicAgentService, config, question: str, channel: str = "chat", session_id: str = "s1"):
    customer = _make_customer()
    events = []
    async for event in service.process_agent_stream(
        db=AsyncMock(),
        site_id="sbal",
        session_id=session_id,
        question=question,
        customer_id=customer.id,
        customer=customer,
        config=config,
        brand_name="SBAL",
        channel=channel,
    ):
        events.append(event)
    return events


# --- Pure builder unit tests ---


def test_services_ui_maps_fields_and_caps_at_limit():
    services = [
        {"id": f"s{i}", "name": f"Service {i}", "price_npr": 1000 + i, "duration_minutes": 30, "description": "d"}
        for i in range(12)
    ]
    ui = _services_ui(services)
    assert len(ui) == 10
    assert ui[0] == {"id": "s0", "name": "Service 0", "price": 1000, "duration": 30, "image_url": None, "description": "d"}


def test_slots_ui_from_open_times_plus_another_day():
    result = {
        "service": {"name": "Lash Lift"},
        "date": "2026-10-10",
        "open_times": ["10:00", "11:00"],
        "next_open_slots": [{"date": "2026-10-11", "time": "09:00"}],
    }
    slots = _slots_ui(result)
    assert slots[0] == {"label": "10:00", "payload": "Book Lash Lift on 2026-10-10 at 10:00"}
    assert slots[1] == {"label": "11:00", "payload": "Book Lash Lift on 2026-10-10 at 11:00"}
    assert slots[-1] == {"label": "Another day", "payload": "What other days is Lash Lift available?"}


def test_slots_ui_no_open_times_falls_back_to_next_open_slots():
    result = {"service": {"name": "Cleaning"}, "next_open_slots": [{"date": "2026-09-25", "time": "14:00"}]}
    slots = _slots_ui(result)
    assert slots == [{"label": "2026-09-25 14:00", "payload": "Book Cleaning on 2026-09-25 at 14:00"}]


def test_slots_ui_tolerates_missing_time_key():
    """Some callers (e.g. a full-day fallback) only promise a date."""
    result = {"service": {"name": "Cleaning"}, "next_open_slots": [{"date": "2026-09-25"}]}
    slots = _slots_ui(result)
    assert slots == [{"label": "2026-09-25", "payload": "Book Cleaning on 2026-09-25 at "}]


def test_slots_ui_empty_when_nothing_available():
    assert _slots_ui({"service": {"name": "Cleaning"}, "open_times": [], "next_open_slots": []}) == []


def test_slots_ui_another_day_label_follows_reply_language():
    result = {
        "service": {"name": "Lash Lift"},
        "date": "2026-10-10",
        "open_times": ["10:00"],
        "next_open_slots": [{"date": "2026-10-11", "time": "09:00"}],
    }
    en = _slots_ui(result, lang="en")
    ne = _slots_ui(result, lang="ne_romanized")
    assert en[-1]["label"] == "Another day"
    assert ne[-1]["label"] == "Arko din"
    # payload (the exact next turn fed back to the agent) is unaffected by display language
    assert en[-1]["payload"] == ne[-1]["payload"]


def test_booking_ui_maps_fields():
    booking = {
        "booking_number": "BK-123",
        "date": "2026-10-10",
        "start_time": "10:00",
        "treatment_name": "Lash Lift",
        "branch_name": "Thamel Branch",
    }
    assert _booking_ui(booking) == {
        "booking_number": "BK-123",
        "service": "Lash Lift",
        "when": "2026-10-10 10:00",
        "name": "Thamel Branch",
    }


# --- Integration: ui on the done event ---


@pytest.mark.asyncio
async def test_list_services_populates_ui_services():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    responses = [
        _stream_tool_call("call_1", "list_services", "{}"),
        _stream("Here are our services."),
    ]
    service = _service_for_responses(responses)
    fake_result = {
        "branch": {"id": "b1", "name": "Thamel Branch"},
        "services": [
            {"id": "svc1", "name": "Lash Lift", "category": "Lashes", "duration_minutes": 60,
             "price_npr": 2500, "description": "A lash lift."},
        ],
    }
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=fake_result)):
        events = await _run(service, config, question="What services do you offer?")

    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["ui"]["services"] == [
        {"id": "svc1", "name": "Lash Lift", "price": 2500, "duration": 60, "image_url": None, "description": "A lash lift."},
    ]


@pytest.mark.asyncio
async def test_check_availability_populates_ui_slots():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    responses = [
        _stream_tool_call("call_1", "check_availability", '{"service": "Lash Lift", "date": "2026-10-10"}'),
        _stream("Here's what's open."),
    ]
    service = _service_for_responses(responses)
    fake_result = {
        "service": {"id": "svc1", "name": "Lash Lift", "duration_minutes": 60, "price_npr": 2500},
        "date": "2026-10-10",
        "open_times": ["10:00", "11:00"],
    }
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=fake_result)):
        events = await _run(service, config, question="Any slots on Oct 10 for a lash lift?")

    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["ui"]["slots"][0] == {"label": "10:00", "payload": "Book Lash Lift on 2026-10-10 at 10:00"}


@pytest.mark.asyncio
async def test_prepare_booking_populates_ui_confirm():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    responses = [
        _stream_tool_call(
            "call_1", "prepare_booking",
            '{"service": "Lash Lift", "date": "2026-10-10", "time": "10:00", '
            '"full_name": "Test User", "phone": "9841234567"}',
        ),
    ]
    service = _service_for_responses(responses)
    fake_result = {
        "summary": "Lash Lift on Saturday, 2026-10-10 at 10:00 for Test User (+9779841234567) at Thamel Branch.",
        "pending_booking": {
            "service_name": "Lash Lift", "date": "2026-10-10", "time": "10:00",
            "full_name": "Test User", "phone_e164": "+9779841234567", "branch_name": "Thamel Branch",
        },
    }
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=fake_result)):
        events = await _run(service, config, question="Yes book the 10am lash lift for Test User, 9841234567")

    done_event = next(e for e in events if e["type"] == "done")
    confirm = done_event["ui"]["confirm"]
    assert confirm["summary"] == fake_result["summary"]
    assert confirm["yes_payload"] == "Yes"
    assert confirm["change_payload"] == "I'd like to change the details"
    assert confirm["yes_label"] == "✅ Confirm"
    assert confirm["change_label"] == "✏️ Change"


@pytest.mark.asyncio
async def test_confirm_booking_populates_ui_booking_and_clears_confirm():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    responses = [_stream_tool_call("call_1", "confirm_booking", "{}")]
    service = _service_for_responses(responses)
    fake_result = {
        "booking": {
            "booking_number": "BK-999", "date": "2026-10-10", "start_time": "10:00",
            "treatment_name": "Lash Lift", "branch_name": "Thamel Branch",
        },
        "confirmed_pending": {
            "service_name": "Lash Lift", "date": "2026-10-10", "time": "10:00",
            "full_name": "Test User", "phone_e164": "+9779841234567", "branch_name": "Thamel Branch",
        },
    }
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=fake_result)):
        events = await _run(service, config, question="Yes")

    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["ui"]["booking"] == {
        "booking_number": "BK-999", "service": "Lash Lift", "when": "2026-10-10 10:00", "name": "Thamel Branch",
    }
    assert "confirm" not in done_event["ui"]


@pytest.mark.asyncio
async def test_voice_channel_done_event_unaffected_by_ui():
    """Voice regression (brief item 2): identical behaviour, `ui` unused —
    the extra key must not change `answer`/`suggestions`/`sources`."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    responses = [
        _stream_tool_call("call_1", "list_services", "{}"),
        _stream("We offer a lash lift."),
    ]
    service = _service_for_responses(responses)
    fake_result = {
        "branch": {"id": "b1", "name": "Thamel Branch"},
        "services": [{"id": "svc1", "name": "Lash Lift", "duration_minutes": 60, "price_npr": 2500}],
    }
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=fake_result)):
        events = await _run(service, config, question="What services do you offer?", channel="voice")

    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["answer"] == "We offer a lash lift."
    assert done_event["suggestions"] == []
    assert done_event["sources"] == []
    # ui is present (built regardless of channel) but voice simply doesn't read it.
    assert "services" in done_event["ui"]


@pytest.mark.asyncio
async def test_no_tool_calls_means_no_ui_key():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    responses = [_stream("We're open 9 to 5.")]
    service = _service_for_responses(responses)

    events = await _run(service, config, question="What are your hours?")

    done_event = next(e for e in events if e["type"] == "done")
    assert "ui" not in done_event
