"""
LLM-ROUNDTRIP-BRIEF §1.3 (brain folder): multiple `check_availability`
calls in ONE iteration run concurrently, not one at a time; any other
tool mix (including a single check_availability, or check_availability
alongside a different tool) still runs sequentially exactly as before.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import ClinicAgentService
from app.models.customer import Customer


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000dd"),
        name="Dental City",
        site_id="dental-city",
        api_key="key",
        website_type="clinic",
    )


def _usage(prompt, completion):
    return SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion
    )


def _usage_only_chunk(prompt, completion):
    return SimpleNamespace(choices=[], usage=_usage(prompt, completion))


def _content_chunk(text):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))],
        usage=None,
    )


def _tool_call_chunk(idx, call_id, name, arguments):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(
            content=None,
            tool_calls=[SimpleNamespace(
                index=idx, id=call_id, function=SimpleNamespace(name=name, arguments=arguments),
            )],
        ))],
        usage=None,
    )


async def _stream_tool_calls(*calls):
    for idx, (call_id, name, arguments) in enumerate(calls):
        yield _tool_call_chunk(idx, call_id, name, arguments)
    yield _usage_only_chunk(prompt=100, completion=10)


async def _stream_text(text):
    yield _content_chunk(text)
    yield _usage_only_chunk(prompt=100, completion=10)


def _bare_service():
    service = ClinicAgentService()
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


async def _run(service, config, question, session_id="s1"):
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
        channel="chat",
        trace_id="trace-abc",
    ):
        events.append(event)
    return events


@pytest.mark.asyncio
async def test_multiple_check_availability_calls_run_concurrently():
    """3 check_availability calls in one iteration must overlap in flight,
    not run strictly one after another."""
    service = _bare_service()
    in_flight = {"count": 0, "max_concurrent": 0}

    def _create(**kw):
        return _stream_tool_calls(
            ("call_1", "check_availability", '{"service": "Cleaning", "date": "2026-09-24"}'),
            ("call_2", "check_availability", '{"service": "Cleaning", "date": "2026-09-25"}'),
            ("call_3", "check_availability", '{"service": "Cleaning", "date": "2026-09-26"}'),
        )

    call_count = {"n": 0}

    async def _create_wrapper(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _create(**kw)
        return _stream_text("Here are the open times.")

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create_wrapper)

    async def _fake_execute_tool(**kw):
        in_flight["count"] += 1
        in_flight["max_concurrent"] = max(in_flight["max_concurrent"], in_flight["count"])
        # Yield control so a truly-concurrent caller would overlap here;
        # a sequential caller would never have more than 1 in flight.
        await asyncio.sleep(0.01)
        in_flight["count"] -= 1
        return {"service": {"name": "Cleaning"}, "date": kw["tool_args"].get("date"), "open_times": []}

    import app.services.clinic_agent as clinic_agent_mod
    clinic_agent_mod.execute_clinic_tool = _fake_execute_tool  # type: ignore[attr-defined]

    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City")
    events = await _run(service, config, question="Is Wed, Thu, or Fri open for cleaning?")

    assert in_flight["max_concurrent"] == 3, (
        "3 check_availability calls in one iteration should overlap; "
        f"max concurrent seen was {in_flight['max_concurrent']}"
    )
    # All 3 tool_call done events still fire, and the turn still completes.
    done_tool_events = [e for e in events if e.get("type") == "tool_call" and e.get("status") == "done"]
    assert len(done_tool_events) == 3
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_single_check_availability_call_unaffected():
    """A lone check_availability call (the common case) still executes
    exactly as before — no gather overhead, no behavior change."""
    service = _bare_service()
    call_count = {"n": 0}

    async def _create(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _stream_tool_calls(("call_1", "check_availability", '{"service": "Cleaning"}'))
        return _stream_text("We have times open Thursday.")

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)

    async def _fake_execute_tool(**kw):
        return {"service": {"name": "Cleaning"}, "next_open_slots": [{"date": "2026-09-25"}]}

    import app.services.clinic_agent as clinic_agent_mod
    clinic_agent_mod.execute_clinic_tool = _fake_execute_tool  # type: ignore[attr-defined]

    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City")
    events = await _run(service, config, question="Any openings for cleaning?")

    done_tool_events = [e for e in events if e.get("type") == "tool_call" and e.get("status") == "done"]
    assert len(done_tool_events) == 1
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_mixed_tool_types_still_run_sequentially():
    """check_availability alongside a different tool in the same iteration
    must NOT be swept into the concurrent path — only the
    all-check_availability case is scoped as safe."""
    service = _bare_service()
    in_flight = {"count": 0, "max_concurrent": 0}
    call_count = {"n": 0}

    async def _create(**kw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _stream_tool_calls(
                ("call_1", "check_availability", '{"service": "Cleaning", "date": "2026-09-24"}'),
                ("call_2", "search_knowledge", '{"query": "parking"}'),
            )
        return _stream_text("Here's what I found.")

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)

    async def _fake_execute_tool(**kw):
        in_flight["count"] += 1
        in_flight["max_concurrent"] = max(in_flight["max_concurrent"], in_flight["count"])
        await asyncio.sleep(0.01)
        in_flight["count"] -= 1
        if kw["tool_name"] == "check_availability":
            return {"service": {"name": "Cleaning"}, "open_times": []}
        return {"chunks": [{"content": "Free parking available."}]}

    import app.services.clinic_agent as clinic_agent_mod
    clinic_agent_mod.execute_clinic_tool = _fake_execute_tool  # type: ignore[attr-defined]

    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City")
    events = await _run(service, config, question="Is cleaning open Wed, and is there parking?")

    assert in_flight["max_concurrent"] == 1, "mixed tool types must still run one at a time"
    assert events[-1]["type"] == "done"
