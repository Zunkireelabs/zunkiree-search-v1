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
from openai import APIConnectionError

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
