"""
SBAL demo-blocker fix: the clinic agent's "chat" OpenAI client profile
(openai_client.py) deliberately carries 0 SDK retries so a single call can
never exceed ~15s inside Orca's voice budget. But a bare timeout on the
first (tool-decision) call, with nothing shown to the visitor yet, is worth
one retry on non-voice channels — voice is the only channel that bound was
protecting.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import NOT_GIVEN, APIConnectionError

from app.models.customer import Customer
from app.services.clinic_agent import ClinicAgentService


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000cc"),
        name="Dental City",
        site_id="dental-city",
        api_key="key",
        website_type="clinic",
    )


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty_result)
    return db


def _timeout_error() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))


def _chunk(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None), finish_reason="stop")],
        usage=None,
    )


async def _ok_stream(text: str):
    yield _chunk(text)


def _service() -> ClinicAgentService:
    service = ClinicAgentService()
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


async def _run(service: ClinicAgentService, channel: str) -> list:
    customer = _make_customer()
    events = []
    with patch("app.services.query.get_query_service") as mock_gqs:
        mock_gqs.return_value._retrieve_and_rank = AsyncMock(return_value={"chunks_for_llm": []})
        async for event in service.process_agent_stream(
            db=_mock_db(),
            site_id="dental-city",
            session_id="s1",
            question="services haru k cha?",
            customer_id=customer.id,
            customer=customer,
            config=None,
            brand_name="Dental City",
            channel=channel,
        ):
            events.append(event)
    return events


@pytest.mark.asyncio
async def test_timeout_on_chat_channel_retries_once_and_recovers():
    service = _service()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(
        side_effect=[_timeout_error(), _ok_stream("Here are our services.")]
    )

    events = await _run(service, channel="chat")

    assert service.client.chat.completions.create.call_count == 2
    tokens = "".join(e["data"] for e in events if e.get("type") == "token")
    assert "Here are our services." in tokens


@pytest.mark.asyncio
async def test_timeout_twice_on_chat_channel_raises_after_one_retry():
    service = _service()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=[_timeout_error(), _timeout_error()])

    with pytest.raises(APIConnectionError):
        await _run(service, channel="chat")

    assert service.client.chat.completions.create.call_count == 2


@pytest.mark.asyncio
async def test_timeout_on_voice_channel_never_retries():
    service = _service()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=[_timeout_error()])

    with pytest.raises(APIConnectionError):
        await _run(service, channel="voice")

    assert service.client.chat.completions.create.call_count == 1


@pytest.mark.asyncio
async def test_chat_channel_uses_8s_per_call_timeout_voice_uses_client_default():
    """
    Review on #126 follow-up: the retry only fits inside IG's 20s lane
    timeout and Orca's 25s widget-run budget if each attempt is shorter
    than the "chat" client profile's default 15s. Non-voice channels pass
    an explicit 8s per-call `timeout` kwarg; voice passes none (NOT_GIVEN),
    keeping the client's own 15s/0-retry default — `timeout=None` would
    instead mean "no timeout at all" to the SDK.
    """
    captured_timeouts = []

    def _record(**kwargs):
        captured_timeouts.append(kwargs.get("timeout"))
        return _ok_stream("Here are our services.")

    for channel in ("chat", "voice"):
        service = _service()
        service.client = AsyncMock()
        service.client.chat.completions.create = AsyncMock(side_effect=_record)
        await _run(service, channel=channel)

    assert captured_timeouts[0] == 8.0
    assert captured_timeouts[1] is NOT_GIVEN


@pytest.mark.asyncio
async def test_retry_uses_fallback_model_and_6s_timeout_not_same_model():
    """
    Demo-hardening (stage evidence 2026-10-07): a same-model retry is more
    likely to hit the same stalled serving infra as the call that just
    timed out. The retry (attempt 2, non-voice only) uses a different
    model — `self.fallback_model` — and a tighter 6s timeout, so the
    worst case (8s + 6s) stays at ~14s.
    """
    service = _service()
    service.client = AsyncMock()
    calls = []

    def _record(**kwargs):
        calls.append({"model": kwargs["model"], "timeout": kwargs.get("timeout")})
        if len(calls) == 1:
            raise _timeout_error()
        return _ok_stream("Here are our services.")

    service.client.chat.completions.create = AsyncMock(side_effect=_record)

    await _run(service, channel="chat")

    assert calls[0] == {"model": service.model, "timeout": 8.0}
    assert calls[1] == {"model": service.fallback_model, "timeout": 6.0}
    assert service.fallback_model != service.model


@pytest.mark.asyncio
async def test_voice_never_uses_fallback_model():
    service = _service()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_timeout_error())

    with pytest.raises(APIConnectionError):
        await _run(service, channel="voice")

    kwargs = service.client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == service.model
    assert kwargs["timeout"] is NOT_GIVEN


@pytest.mark.asyncio
async def test_latency_log_records_which_model_answered(caplog):
    service = _service()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(
        side_effect=[_timeout_error(), _ok_stream("Here are our services.")]
    )

    with caplog.at_level("INFO", logger="zunkiree.clinic_agent"):
        await _run(service, channel="chat")

    final_answer_logs = [
        r.message for r in caplog.records
        if "[CLINIC-LATENCY] llm_call " in r.message and "kind=final_answer" in r.message
    ]
    assert len(final_answer_logs) == 1
    assert f"model={service.fallback_model}" in final_answer_logs[0]


class _FakeMonotonicClock:
    """A controllable stand-in for time.monotonic() — advances only when
    told to, so a test can simulate "this call burned N seconds" without
    an real sleep."""

    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_timeout_then_retry_finishes_under_20s_with_mocked_clock():
    service = _service()
    service.client = AsyncMock()
    clock = _FakeMonotonicClock()
    call_count = {"n": 0}

    def _side_effect(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Burns the full 8s per-call timeout before failing.
            clock.advance(8.0)
            raise _timeout_error()
        # Retry (fallback model, 6s budget) succeeds just inside it.
        clock.advance(5.5)
        return _ok_stream("Here are our services.")

    service.client.chat.completions.create = AsyncMock(side_effect=_side_effect)

    with patch("time.monotonic", clock):
        events = await _run(service, channel="chat")

    assert service.client.chat.completions.create.call_count == 2
    tokens = "".join(e["data"] for e in events if e.get("type") == "token")
    assert "Here are our services." in tokens
    # The clock only advances inside the mocked LLM calls (8.0 + 5.5 = 13.5s,
    # under the ~14s worst case of an 8s timeout + 6s retry), well under
    # IG's 20s lane timeout / Orca's 25s widget-run budget.
    assert clock.now < 20.0
