"""
SBAL demo-hardening: a visitor-facing /query/stream failure used to say "An
error occurred processing your request" regardless of cause or channel —
not honest ("an error" isn't what happened; the visitor just waited) and not
localized. Every non-voice channel (chat, instagram, or omitted) now gets a
friendly, truthful message in the turn's own detected language. Voice is
unchanged — Orca has its own turn-failure handling.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.api.query import QueryRequest, _stream_failure_message, submit_query_stream


def _make_customer():
    customer = MagicMock()
    customer.id = uuid4()
    customer.name = "Test Co"
    customer.website_type = "generic"
    return customer


def _fake_request() -> SimpleNamespace:
    return SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))


async def _failing_stream(**kwargs):
    raise RuntimeError("boom")
    yield  # pragma: no cover - makes this an async generator


async def _collect_sse(response) -> str:
    body = b""
    async for chunk in response.body_iterator:
        body += chunk if isinstance(chunk, bytes) else chunk.encode()
    return body.decode()


@pytest.mark.parametrize(
    ("question", "expected_key"),
    [
        ("what services do you have?", "en"),
        ("services haru k cha?", "ne_romanized"),
        ("सेवाहरू के छन्?", "ne_devanagari"),
        # Review on #131: mixed_ne_en is Latin-script code-switching ("is it
        # cha?") — those visitors type romanized, not Devanagari.
        ("is it cha?", "ne_romanized"),
    ],
)
def test_stream_failure_message_matches_turn_language(question, expected_key):
    assert _stream_failure_message(question) == {
        "en": "Sorry, I took too long to answer. Could you send that again?",
        "ne_romanized": "Maaf garnuhos, jawaph dina dherai samaya lagyo. Feri sodhna milcha?",
        "ne_devanagari": "माफ गर्नुहोस्, जवाफ दिन धेरै समय लाग्यो। फेरि सोध्न मिल्छ?",
    }[expected_key]


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", [None, "chat", "instagram"])
async def test_non_voice_stream_failure_is_friendly_not_generic(channel):
    customer = _make_customer()
    with patch("app.api.query.get_query_service") as mock_gqs:
        mock_gqs.return_value._get_customer = AsyncMock(return_value=customer)
        mock_gqs.return_value._get_widget_config = AsyncMock(return_value=None)
        mock_gqs.return_value.process_query_stream = _failing_stream

        query = QueryRequest(site_id="dental-city", question="what services do you have?", channel=channel)
        response = await submit_query_stream(request=_fake_request(), query=query, db=AsyncMock())
        body = await _collect_sse(response)

    assert "An error occurred processing your request" not in body
    assert "Sorry, I took too long to answer. Could you send that again?" in body


@pytest.mark.asyncio
async def test_voice_stream_failure_message_is_unchanged():
    customer = _make_customer()
    with patch("app.api.query.get_query_service") as mock_gqs:
        mock_gqs.return_value._get_customer = AsyncMock(return_value=customer)
        mock_gqs.return_value._get_widget_config = AsyncMock(return_value=None)
        mock_gqs.return_value.process_query_stream = _failing_stream

        query = QueryRequest(site_id="dental-city", question="what services do you have?", channel="voice")
        response = await submit_query_stream(request=_fake_request(), query=query, db=AsyncMock())
        body = await _collect_sse(response)

    assert "An error occurred processing your request" in body
