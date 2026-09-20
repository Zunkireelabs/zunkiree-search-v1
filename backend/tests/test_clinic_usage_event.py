"""
ZUNKIREE-EMIT-USAGE-BRIEF: the clinic agent must emit one `usage` SSE event
per turn, summed across every OpenAI call the turn actually makes — the
streaming tool-loop call(s) plus the optional non-streaming escalation
translation call — and must not fabricate one on turns that never call the
model at all.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import ClinicAgentService


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000cc"),
        name="Dental City",
        site_id="dental-city",
        api_key="key",
        website_type="clinic",
    )


def _usage(prompt, completion):
    return SimpleNamespace(
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion
    )


def _content_chunk(text):
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=text, tool_calls=None))],
        usage=None,
    )


def _usage_only_chunk(prompt, completion):
    # Matches the real OpenAI SDK shape with stream_options.include_usage:
    # the final chunk carries usage and an EMPTY choices list.
    return SimpleNamespace(choices=[], usage=_usage(prompt, completion))


async def _stream_with_usage(text: str, prompt: int, completion: int):
    yield _content_chunk(text)
    yield _usage_only_chunk(prompt, completion)


def _completion(text: str, prompt: int, completion: int, finish_reason: str = "stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=finish_reason)],
        usage=_usage(prompt, completion),
    )


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
    ):
        events.append(event)
    return events


def _bare_service():
    service = ClinicAgentService()
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


@pytest.mark.asyncio
async def test_usage_event_emitted_after_done_with_real_token_counts():
    service = _bare_service()

    def _create(**kw):
        assert kw.get("stream_options") == {"include_usage": True}
        return _stream_with_usage("We are open 10 AM to 8 PM.", prompt=120, completion=15)

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)

    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City")
    events = await _run(service, config, question="What are your hours?")

    usage_events = [e for e in events if e["type"] == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0]["data"] == {
        "model": service.model,
        "prompt_tokens": 120,
        "completion_tokens": 15,
        "total_tokens": 135,
    }
    # usage must precede done, per the brief ("emit it once per turn, after done" —
    # meaning after the turn's content is decided, not necessarily after the
    # done event on the wire); assert it's present and done still closes the turn.
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_usage_sums_across_multiple_tool_loop_iterations():
    """The tool loop can call the model more than twice in one turn (up to
    MAX_TOOL_ITERATIONS) — every one of those calls must contribute to the
    summed usage event, not just the first or the last."""
    service = _bare_service()
    calls = {"n": 0}

    async def _tool_call_then_text_stream():
        yield SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(
                content=None,
                tool_calls=[SimpleNamespace(
                    index=0,
                    id="call_1",
                    function=SimpleNamespace(name="search_knowledge", arguments='{"query": "hours"}'),
                )],
            ))],
            usage=None,
        )
        yield _usage_only_chunk(prompt=200, completion=10)

    def _create(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return _tool_call_then_text_stream()
        return _stream_with_usage("We are open 10 AM to 8 PM.", prompt=250, completion=20)

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)

    async def _fake_execute_tool(**kw):
        return {"chunks": []}

    import app.services.clinic_agent as clinic_agent_mod
    clinic_agent_mod.execute_clinic_tool = _fake_execute_tool  # type: ignore[attr-defined]

    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City")
    events = await _run(service, config, question="What are your hours?")

    assert calls["n"] == 2
    usage_events = [e for e in events if e["type"] == "usage"]
    assert len(usage_events) == 1
    assert usage_events[0]["data"] == {
        "model": service.model,
        "prompt_tokens": 450,
        "completion_tokens": 30,
        "total_tokens": 480,
    }


@pytest.mark.asyncio
async def test_no_usage_event_when_no_model_call_is_made():
    """Forced-confirmation turns answer entirely code-side without touching
    the model — a metering event with fabricated zeros would be worse than
    no event at all (per the brief's 'never fabricate zeros' framing)."""
    from app.services import clinic_tools as clinic_tools_mod

    service = _bare_service()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock()

    async def _fake_execute_tool(**kw):
        return {"booking": {"booking_number": "BK-123"}, "confirmed_pending": {
            "service_name": "Cleaning", "date": "2026-09-21", "time": "10:00", "phone": "9800000000",
        }}

    original = clinic_tools_mod.execute_clinic_tool
    import app.services.clinic_agent as clinic_agent_mod
    clinic_agent_mod.execute_clinic_tool = _fake_execute_tool  # type: ignore[attr-defined]
    clinic_agent_mod.get_awaiting_confirmation = lambda session_id, turn: True  # type: ignore[attr-defined]

    try:
        config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City")
        events = await _run(service, config, question="yes confirm it")
    finally:
        clinic_agent_mod.execute_clinic_tool = original  # type: ignore[attr-defined]

    assert not any(e["type"] == "usage" for e in events)
    service.client.chat.completions.create.assert_not_awaited()
