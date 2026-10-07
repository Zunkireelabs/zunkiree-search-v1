"""
SBAL-Z6: when a tenant's `widget_configs.service_cards` flag is on (sbal
only today), a multi-service match skips the model's own enumerated-list
generation — `full_answer` becomes just the localized `services_caption`
(the widget renders cards from `ui.services` instead; IG already ignores
the model's text on this turn per SBAL-Z5). This is a pure latency win:
one fewer LLM completion call for "what services do you have?"-shaped
turns. Tenants without the flag (dental-city) are completely unaffected —
same number of LLM calls, same enumerated-list answer, as before this brief.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services import clinic_tools
from app.services.clinic_agent import ClinicAgentService


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000ee"),
        name="Sami's Brow and Lashes",
        site_id="sbal",
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


def _tool_call_chunk(call_id, name, arguments):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(index=0, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))],
    ))])


async def _stream(text: str):
    yield _chunk(content=text)


async def _stream_tool_call(call_id, name, arguments):
    yield _tool_call_chunk(call_id, name, arguments)


def _service_for_responses(responses: list) -> ClinicAgentService:
    service = ClinicAgentService()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=lambda **kw: responses.pop(0))
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


async def _run(service, config, question, session_id, channel="chat"):
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
        brand_name="Sami's Brow and Lashes",
        channel=channel,
    ):
        events.append(event)
    return events


MANY_SERVICES = {
    "branch": {"id": "b1", "name": "Thamel"},
    "services": [
        {"id": "svc-1", "name": "Highly Defining Dye", "category": "Brow",
         "duration_minutes": 45, "price_npr": 1200, "description": "A bold brow tint."},
        {"id": "svc-2", "name": "Lash Lift", "category": "Lash",
         "duration_minutes": 60, "price_npr": 2500, "description": "Lift and set."},
    ],
}


SIXTEEN_SERVICES = {
    "branch": {"id": "b1", "name": "Thamel"},
    "services": [
        {"id": f"svc-{i}", "name": f"Service {i}", "category": "Misc",
         "duration_minutes": 30, "price_npr": 1000 + i, "description": "d"}
        for i in range(16)
    ],
}


@pytest.mark.asyncio
async def test_widget_channel_returns_all_sixteen_services():
    """SBAL-Z7: Meta's carousel caps at 10 — the widget has no such limit
    (sbal has 16 services) and must show all of them, not the old
    across-the-board cap-at-10."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None, service_cards=True)
    service = _service_for_responses([
        _stream_tool_call("call_1", "list_services", "{}"),
    ])

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=SIXTEEN_SERVICES)):
        events = await _run(service, config, "what services do you have?", session_id="widget-limit-1", channel="chat")

    done_event = next(e for e in events if e["type"] == "done")
    assert len(done_event["ui"]["services"]) == 16


@pytest.mark.asyncio
async def test_instagram_channel_still_caps_at_ten():
    """Regression: IG/Messenger keep Meta's carousel limit."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None, service_cards=True)
    service = _service_for_responses([
        _stream_tool_call("call_1", "list_services", "{}"),
    ])

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=SIXTEEN_SERVICES)):
        events = await _run(
            service, config, "what services do you have?", session_id="widget-limit-2", channel="instagram",
        )

    done_event = next(e for e in events if e["type"] == "done")
    assert len(done_event["ui"]["services"]) == 10


@pytest.mark.asyncio
async def test_flag_on_skips_second_llm_call_for_multi_match():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None, service_cards=True)
    # Only ONE response queued — if the shortcut didn't fire, the second
    # (missing) completions.create call would raise IndexError via .pop(0).
    service = _service_for_responses([
        _stream_tool_call("call_1", "list_services", '{"query": "lash"}'),
    ])

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=MANY_SERVICES)):
        events = await _run(service, config, "what services do you have?", session_id="widget-1")

    assert service.client.chat.completions.create.await_count == 1
    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["answer"] == "Here are our services — swipe to see them."
    assert len(done_event["ui"]["services"]) == 2
    token_events = [e["data"] for e in events if e["type"] == "token"]
    assert token_events == ["Here are our services — swipe to see them."]


@pytest.mark.asyncio
async def test_flag_off_keeps_full_two_call_enumerated_answer():
    """Regression: dental-city (flag off) gets EXACTLY today's behaviour —
    two LLM calls, the model's own (possibly long) enumerated text."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None, service_cards=False)
    service = _service_for_responses([
        _stream_tool_call("call_1", "list_services", '{"query": "lash"}'),
        _stream("1. Highly Defining Dye - NPR 1200\n2. Lash Lift - NPR 2500"),
    ])

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=MANY_SERVICES)):
        events = await _run(service, config, "what services do you have?", session_id="widget-2")

    assert service.client.chat.completions.create.await_count == 2
    done_event = next(e for e in events if e["type"] == "done")
    assert "Highly Defining Dye" in done_event["answer"]
    assert done_event["ui"]["services"]


@pytest.mark.asyncio
async def test_flag_on_but_voice_channel_keeps_full_answer():
    """Guardrail: voice is unchanged by this brief regardless of the flag —
    voice never shows cards, so there's nothing to shortcut to."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None, service_cards=True)
    service = _service_for_responses([
        _stream_tool_call("call_1", "list_services", '{"query": "lash"}'),
        _stream("We offer Highly Defining Dye and Lash Lift."),
    ])

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=MANY_SERVICES)):
        events = await _run(
            service, config, "what services do you have?", session_id="widget-3", channel="voice",
        )

    assert service.client.chat.completions.create.await_count == 2
    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["answer"] == "We offer Highly Defining Dye and Lash Lift."


@pytest.mark.asyncio
async def test_flag_on_single_match_is_unaffected_by_shortcut():
    """A single-service match still goes through the normal service_detail
    path (SBAL-Z5) — the Z6 shortcut only applies to a real multi-match."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None, service_cards=True)
    one_service = {
        "branch": {"id": "b1", "name": "Thamel"},
        "services": [MANY_SERVICES["services"][0]],
    }
    service = _service_for_responses([
        _stream_tool_call("call_1", "list_services", '{"query": "Highly Defining Dye"}'),
        _stream("Highly Defining Dye is NPR 1200 and takes 45 minutes."),
    ])

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=one_service)):
        events = await _run(
            service, config, "tell me about highly defining dye", session_id="widget-4",
        )

    assert service.client.chat.completions.create.await_count == 2
    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["ui"]["service_detail"]["name"] == "Highly Defining Dye"
