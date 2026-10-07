"""
SBAL-Z2: a clinic tenant's DM is routed to `_process_booking_agent_message`,
which calls the clinic lane over HTTP (never in-process — the confirmation
gate is in-process-memory state, correct only with one worker per process;
the prod API runs 2). Covers: SSE parsing of the lane's `done` event into
answer/suggestions/ui, the unconfigured-lane and lane-error fallbacks (never
silence), first-DM name greeting, and that ecommerce/kasa's routing is
unchanged.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chatbot_query import ChatbotQueryService


def _make_service():
    svc = ChatbotQueryService.__new__(ChatbotQueryService)
    svc.conversation_service = MagicMock()
    svc.conversation_service.get_history = AsyncMock(return_value=[])
    svc.conversation_service.add_message = AsyncMock()
    svc.llm_service = MagicMock()
    return svc


def _make_channel(channel_id="ch-1"):
    ch = MagicMock()
    ch.id = channel_id
    ch.config = {}
    return ch


class _FakeStreamResponse:
    def __init__(self, status_code, lines):
        self.status_code = status_code
        self._lines = lines

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient: `async with ... as client:` then
    `client.stream("POST", url, json=...)` is itself an async context
    manager yielding the response."""

    def __init__(self, response: _FakeStreamResponse, captured: dict):
        self._response = response
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, json=None):
        self._captured["method"] = method
        self._captured["url"] = url
        self._captured["json"] = json
        return self._response


def _sse(*events):
    return [f"data: {json.dumps(e)}" for e in events]


async def _call(svc, response_lines, status_code=200, clinic_lane_url="http://zunkiree-clinic-prod:8000", **kwargs):
    captured = {}
    fake_response = _FakeStreamResponse(status_code, response_lines)

    settings = MagicMock()
    settings.clinic_lane_url = clinic_lane_url
    settings.clinic_lane_timeout_seconds = 20.0

    with patch("app.services.chatbot_query.get_settings", return_value=settings), \
         patch("httpx.AsyncClient", return_value=_FakeAsyncClient(fake_response, captured)):
        result = await svc._process_booking_agent_message(
            db=AsyncMock(),
            channel=_make_channel(),
            site_id="sbal",
            sender_id="sender-1",
            message_text="Book a lash lift",
            start=0.0,
            **kwargs,
        )
    return result, captured


@pytest.mark.asyncio
async def test_parses_done_event_answer_suggestions_and_ui():
    ui = {"services": [{"id": "s1", "name": "Lash Lift"}]}
    lines = _sse(
        {"type": "token", "data": "Here"},
        {"type": "done", "answer": "Here are our services.", "suggestions": ["Book now"], "ui": ui},
    )
    result, captured = await _call(svc=_make_service(), response_lines=lines)

    assert result["answer"] == "Here are our services."
    assert result["suggestions"] == ["Book now"]
    assert result["ui"] == ui
    assert captured["json"]["site_id"] == "sbal"
    assert captured["json"]["channel"] == "instagram"
    assert captured["json"]["session_id"] == "dm:ch-1:sender-1"
    assert captured["url"].endswith("/api/v1/query/stream")


@pytest.mark.asyncio
async def test_no_ui_key_when_lane_omits_it():
    lines = _sse({"type": "done", "answer": "We're open 9 to 5.", "suggestions": []})
    result, _ = await _call(svc=_make_service(), response_lines=lines)
    assert result["ui"] is None


@pytest.mark.asyncio
async def test_unconfigured_lane_url_returns_fallback_never_silent():
    result, captured = await _call(svc=_make_service(), response_lines=[], clinic_lane_url="")
    assert result["answer"]  # never empty/silent
    assert "try again" in result["answer"].lower() or "contact" in result["answer"].lower()
    assert captured == {}  # never even attempted the HTTP call


@pytest.mark.asyncio
async def test_lane_non_200_returns_polite_fallback_never_silent():
    result, _ = await _call(svc=_make_service(), response_lines=[], status_code=503)
    assert result["answer"]
    assert "trouble" in result["answer"].lower() or "try again" in result["answer"].lower()


@pytest.mark.asyncio
async def test_lane_error_event_returns_polite_fallback_never_silent():
    lines = _sse({"type": "error", "message": "boom"})
    result, _ = await _call(svc=_make_service(), response_lines=lines)
    assert result["answer"]
    assert "trouble" in result["answer"].lower() or "try again" in result["answer"].lower()


@pytest.mark.asyncio
async def test_first_dm_greets_by_name_once():
    lines = _sse({"type": "done", "answer": "We offer a lash lift.", "suggestions": []})
    result, _ = await _call(svc=_make_service(), response_lines=lines, greet_name="Priya")
    assert result["answer"] == "Hi Priya! We offer a lash lift."


@pytest.mark.asyncio
async def test_no_greet_name_on_later_turns():
    lines = _sse({"type": "done", "answer": "We offer a lash lift.", "suggestions": []})
    result, _ = await _call(svc=_make_service(), response_lines=lines, greet_name=None)
    assert result["answer"] == "We offer a lash lift."


@pytest.mark.asyncio
async def test_persists_assistant_reply():
    svc = _make_service()
    lines = _sse({"type": "done", "answer": "We offer a lash lift.", "suggestions": []})
    await _call(svc=svc, response_lines=lines)
    svc.conversation_service.add_message.assert_awaited_once()
    args = svc.conversation_service.add_message.await_args.args
    assert args[-2] == "assistant"
    assert args[-1] == "We offer a lash lift."


# ---------------------------------------------------------------------------
# Routing regression: ecommerce/kasa unchanged, clinic goes to the new path.
# ---------------------------------------------------------------------------


def _widget_config(website_type):
    cfg = MagicMock()
    cfg.brand_name = "Test"
    cfg.tone = "neutral"
    cfg.fallback_message = "fallback"
    cfg.contact_email = None
    cfg.contact_phone = None
    cfg.welcome_message = None
    cfg.supported_languages = None
    cfg.quick_actions = None
    return cfg


@pytest.mark.asyncio
async def test_ecommerce_tenant_still_routes_to_process_ecommerce_message():
    svc = _make_service()
    svc.conversation_service.get_history = AsyncMock(return_value=[{"role": "user", "content": "hi"}])

    customer = MagicMock()
    customer.id = "cust-1"
    customer.is_active = True
    customer.site_id = "kasa"
    customer.website_type = "ecommerce"

    config = _widget_config("ecommerce")

    db = AsyncMock()
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = config
    db.get = AsyncMock(return_value=customer)
    db.execute = AsyncMock(return_value=config_result)

    with patch.object(svc, "_process_ecommerce_message", AsyncMock(return_value={"answer": "ok"})) as mock_ecom, \
         patch.object(svc, "_process_booking_agent_message", AsyncMock()) as mock_clinic:
        result = await svc.process_message(
            db=db, channel=_make_channel(), sender_id="s1", message_text="Show me shirts",
        )

    mock_ecom.assert_awaited_once()
    mock_clinic.assert_not_awaited()
    assert result == {"answer": "ok"}


@pytest.mark.asyncio
async def test_clinic_tenant_routes_to_booking_agent_message():
    svc = _make_service()
    svc.conversation_service.get_history = AsyncMock(return_value=[{"role": "user", "content": "hi"}])

    customer = MagicMock()
    customer.id = "cust-2"
    customer.is_active = True
    customer.site_id = "sbal"
    customer.website_type = "clinic"

    config = _widget_config("clinic")

    db = AsyncMock()
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = config
    db.get = AsyncMock(return_value=customer)
    db.execute = AsyncMock(return_value=config_result)

    with patch.object(svc, "_process_ecommerce_message", AsyncMock()) as mock_ecom, \
         patch.object(svc, "_process_booking_agent_message", AsyncMock(return_value={"answer": "ok"})) as mock_clinic:
        result = await svc.process_message(
            db=db, channel=_make_channel(), sender_id="s1", message_text="Book a lash lift",
        )

    mock_clinic.assert_awaited_once()
    mock_ecom.assert_not_awaited()
    assert result == {"answer": "ok"}
    # site_id threaded through, not re-derived inside the HTTP-call method
    assert mock_clinic.await_args.kwargs["site_id"] == "sbal"


@pytest.mark.asyncio
async def test_first_clinic_dm_threads_sender_first_name_as_greet_name():
    """Brief item 6: first DM greets by IG first name, once — later turns
    (history non-empty) must not re-greet."""
    svc = _make_service()
    svc.conversation_service.get_history = AsyncMock(return_value=[])  # first message

    customer = MagicMock()
    customer.id = "cust-3"
    customer.is_active = True
    customer.site_id = "sbal"
    customer.website_type = "clinic"

    config = _widget_config("clinic")
    channel = _make_channel()
    channel.platform = "instagram"

    db = AsyncMock()
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = config
    db.get = AsyncMock(return_value=customer)
    db.execute = AsyncMock(return_value=config_result)

    profile = MagicMock()
    profile.name = "Priya Sharma"

    with patch.object(svc, "_process_booking_agent_message", AsyncMock(return_value={"answer": "ok"})) as mock_clinic, \
         patch("app.services.chatbot_query.get_sender_profile_service") as mock_profile_svc:
        mock_profile_svc.return_value.get_or_fetch = AsyncMock(return_value=profile)
        await svc.process_message(db=db, channel=channel, sender_id="s1", message_text="Book a lash lift")

    assert mock_clinic.await_args.kwargs["greet_name"] == "Priya"


@pytest.mark.asyncio
async def test_first_clinic_dm_skips_one_letter_name():
    """SBAL-Z3 P6: "Hi H!" came from a one-letter IG display name (a first
    initial, an emoji-stripped stub, etc.) — greet without a name instead."""
    svc = _make_service()
    svc.conversation_service.get_history = AsyncMock(return_value=[])

    customer = MagicMock()
    customer.id = "cust-5"
    customer.is_active = True
    customer.site_id = "sbal"
    customer.website_type = "clinic"

    config = _widget_config("clinic")
    channel = _make_channel()
    channel.platform = "instagram"

    db = AsyncMock()
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = config
    db.get = AsyncMock(return_value=customer)
    db.execute = AsyncMock(return_value=config_result)

    profile = MagicMock()
    profile.name = "H"

    with patch.object(svc, "_process_booking_agent_message", AsyncMock(return_value={"answer": "ok"})) as mock_clinic, \
         patch("app.services.chatbot_query.get_sender_profile_service") as mock_profile_svc:
        mock_profile_svc.return_value.get_or_fetch = AsyncMock(return_value=profile)
        await svc.process_message(db=db, channel=channel, sender_id="s1", message_text="Book a lash lift")

    assert mock_clinic.await_args.kwargs["greet_name"] is None


@pytest.mark.asyncio
async def test_later_clinic_dm_does_not_greet_by_name():
    svc = _make_service()
    svc.conversation_service.get_history = AsyncMock(return_value=[{"role": "user", "content": "hi"}])

    customer = MagicMock()
    customer.id = "cust-4"
    customer.is_active = True
    customer.site_id = "sbal"
    customer.website_type = "clinic"

    config = _widget_config("clinic")
    channel = _make_channel()
    channel.platform = "instagram"

    db = AsyncMock()
    config_result = MagicMock()
    config_result.scalar_one_or_none.return_value = config
    db.get = AsyncMock(return_value=customer)
    db.execute = AsyncMock(return_value=config_result)

    with patch.object(svc, "_process_booking_agent_message", AsyncMock(return_value={"answer": "ok"})) as mock_clinic:
        await svc.process_message(db=db, channel=channel, sender_id="s1", message_text="What times are open?")

    assert mock_clinic.await_args.kwargs["greet_name"] is None
