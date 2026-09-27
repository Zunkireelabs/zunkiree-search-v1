"""
P4 B1 (P4-VOICE-FEEL-BRIEF §2): hard cap on the service-guess fan-out.
Prod incident: guess "Teeth Cleaning" -> check_availability -> list_services
-> guess "General Dentistry" -> check_availability again = 4 iterations,
12.5s. Prompt wording alone isn't reliable
(llm_prompt_mandate_vs_actual_behavior), so clinic_agent.py enforces this
in code: once a check_availability call has failed to resolve this turn,
any further check_availability/list_services calls are intercepted rather
than actually run against ClinicMD.
"""
import uuid
from unittest.mock import AsyncMock

import pytest

from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import ClinicAgentService
from app.models.customer import Customer

from tests.test_clinic_parallel_availability import (
    _stream_tool_calls, _stream_text, _bare_service,
)


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000dd"),
        name="Dental City", site_id="dental-city", api_key="key", website_type="clinic",
    )


async def _run(service, config, question):
    customer = _make_customer()
    events = []
    async for event in service.process_agent_stream(
        db=AsyncMock(), site_id="dental-city", session_id="s1", question=question,
        customer_id=customer.id, customer=customer, config=config,
        brand_name="Dental City", channel="chat", trace_id="trace-abc",
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_second_check_availability_after_unresolved_guess_is_blocked(caplog):
    """The exact prod pattern: iteration 1 guesses a service name that
    doesn't resolve, iteration 2 tries a different guess. The 2nd
    check_availability must never reach execute_clinic_tool."""
    service = _bare_service()
    call_count = {"n": 0}

    async def _create(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _stream_tool_calls(("call_1", "check_availability", '{"service": "Teeth Cleaning"}'))
        if call_count["n"] == 2:
            return _stream_tool_calls(("call_2", "check_availability", '{"service": "General Dentistry"}'))
        return _stream_text("Which service would you like to check?")

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)

    executed = []

    async def _fake_execute_tool(**kw):
        executed.append(kw["tool_args"].get("service"))
        return {"error": "SERVICE_NOT_FOUND", "message": "Couldn't find a service matching that."}

    import app.services.clinic_agent as clinic_agent_mod
    clinic_agent_mod.execute_clinic_tool = _fake_execute_tool  # type: ignore[attr-defined]

    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City")
    events = await _run(service, config, question="book me a cleaning")

    # Only the FIRST guess ever reached execute_clinic_tool.
    assert executed == ["Teeth Cleaning"]
    assert call_count["n"] == 3
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_list_services_after_resolved_check_availability_is_blocked():
    """Measured on stage: "book me a cleaning" resolved fine on the first
    check_availability call, then the model ALSO called list_services —
    a real extra iteration/round trip for info already in hand. That
    second call must be intercepted."""
    service = _bare_service()
    call_count = {"n": 0}

    async def _create(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _stream_tool_calls(("call_1", "check_availability", '{"service": "Cleaning"}'))
        if call_count["n"] == 2:
            return _stream_tool_calls(("call_2", "list_services", '{}'))
        return _stream_text("Cleaning is open Thursday at 10am.")

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)

    executed = []

    async def _fake_execute_tool(**kw):
        executed.append(kw["tool_name"])
        return {"service": {"name": "Cleaning"}, "next_open_slots": [{"date": "2026-09-25", "time": "10:00"}]}

    import app.services.clinic_agent as clinic_agent_mod
    clinic_agent_mod.execute_clinic_tool = _fake_execute_tool  # type: ignore[attr-defined]

    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City")
    events = await _run(service, config, question="book me a cleaning")

    # list_services never actually executed — only check_availability did.
    assert executed == ["check_availability"]
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_unaffected_when_service_resolves_on_first_try():
    """A single, cleanly-resolved check_availability call (the common case)
    is completely unaffected — no blocking, no behaviour change."""
    service = _bare_service()

    async def _create(**kw):
        return _stream_tool_calls(("call_1", "check_availability", '{"service": "General Dentistry"}'))

    service.client = AsyncMock()
    call_n = {"n": 0}

    async def _create_wrapper(**kw):
        call_n["n"] += 1
        if call_n["n"] == 1:
            return await _create(**kw)
        return _stream_text("Monday at 2pm is open.")

    service.client.chat.completions.create = AsyncMock(side_effect=_create_wrapper)

    async def _fake_execute_tool(**kw):
        return {"service": {"name": "General Dentistry"}, "next_open_slots": [{"date": "2026-09-29", "time": "14:00"}]}

    import app.services.clinic_agent as clinic_agent_mod
    clinic_agent_mod.execute_clinic_tool = _fake_execute_tool  # type: ignore[attr-defined]

    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City")
    events = await _run(service, config, question="is General Dentistry free on Monday?")

    done_tool_events = [e for e in events if e.get("type") == "tool_call" and e.get("status") == "done"]
    assert len(done_tool_events) == 1
    assert events[-1]["type"] == "done"
