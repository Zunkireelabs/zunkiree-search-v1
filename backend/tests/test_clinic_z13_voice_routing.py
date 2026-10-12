"""SBAL-Z13: F7 voice prefetch bound, F8 empty prefetch is recoverable, F9 no
markdown to TTS, F10 a bare Latin token cannot flip the sticky language."""
import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.widget_config import WidgetConfig
from app.services import clinic_agent, clinic_tools
from app.services.clinic_agent import ClinicAgentService, strip_markdown_for_voice, _VoiceMarkdownStripper
from tests.test_clinic_faq_collapse import _make_customer, _stream, _reset_state  # noqa: F401


async def _run(service, question, session_id, channel):
    customer = _make_customer()
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    events = []
    async for e in service.process_agent_stream(
        db=AsyncMock(), site_id="dental-city", session_id=session_id, question=question,
        customer_id=customer.id, customer=customer, config=config,
        brand_name="Dental City", channel=channel,
    ):
        events.append(e)
    return events


def _service(captured, text="Okay."):
    def _create(**kw):
        captured.append(kw)
        return _stream(text)
    s = ClinicAgentService()
    s.client = AsyncMock()
    s.client.chat.completions.create = AsyncMock(side_effect=_create)
    s.conversation_store = AsyncMock()
    s.conversation_store.get_messages = lambda session_id: []
    s.conversation_store.add_message = lambda *a, **kw: None
    return s


@pytest.fixture(autouse=True)
def _not_awaiting_confirmation():
    # test_clinic_usage_event.py permanently monkeypatches this to a lambda
    # returning True; pin it so these tests don't depend on file order.
    with patch.object(clinic_agent, "get_awaiting_confirmation", lambda session_id, turn: False):
        yield


FAQ = "What are your opening hours?"


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["chat", "voice"])
async def test_f8_zero_chunks_injects_nothing_and_keeps_search_knowledge(channel):
    captured = []
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value={"chunks": []})):
        await _run(_service(captured), FAQ, f"z13-f8-{channel}", channel)
    assert "KNOWLEDGE-THIS-TURN" not in captured[0]["messages"][0]["content"]
    assert "found nothing" not in captured[0]["messages"][0]["content"]
    assert "search_knowledge" in {t["function"]["name"] for t in captured[0]["tools"]}


@pytest.mark.asyncio
async def test_f7_voice_slow_prefetch_is_abandoned_with_full_tools(caplog):
    captured = []

    async def slow(**kw):
        await asyncio.sleep(10)
        return {"chunks": [{"content": "late"}]}

    with patch.object(clinic_agent, "VOICE_KNOWLEDGE_PREFETCH_TIMEOUT_S", 0.05), \
         patch("app.services.clinic_agent.execute_clinic_tool", side_effect=slow):
        with caplog.at_level("INFO"):
            await _run(_service(captured), FAQ, "z13-f7-voice", "voice")
    assert "knowledge_prefetch_abandoned" in caplog.text
    assert "KNOWLEDGE-THIS-TURN" not in captured[0]["messages"][0]["content"]
    assert "search_knowledge" in {t["function"]["name"] for t in captured[0]["tools"]}


@pytest.mark.asyncio
async def test_f7_chat_is_not_bounded(caplog):
    captured = []

    async def slow(**kw):
        await asyncio.sleep(0.15)
        return {"chunks": [{"content": "Hours: 10-8."}]}

    with patch.object(clinic_agent, "VOICE_KNOWLEDGE_PREFETCH_TIMEOUT_S", 0.05), \
         patch("app.services.clinic_agent.execute_clinic_tool", side_effect=slow):
        with caplog.at_level("INFO"):
            await _run(_service(captured), FAQ, "z13-f7-chat", "chat")
    assert "knowledge_prefetch_abandoned" not in caplog.text
    assert "Hours: 10-8." in captured[0]["messages"][0]["content"]
    assert "search_knowledge" not in {t["function"]["name"] for t in captured[0]["tools"]}


def test_f9_strips_markdown_for_voice():
    text = "Our services:\n1. **Lashes** - 500\n2. Facial\n- item\n* other\n# Heading\nPlain 1.5 hours."
    out = strip_markdown_for_voice(text)
    for bad in ("1.", "2.", "**", "* ", "#"):
        assert bad not in out.replace("1.5", "")
    assert not any(l.startswith(("- ", "-")) for l in out.splitlines())
    assert "Lashes - 500" in out
    assert "Lashes" in out and "Plain 1.5 hours." in out


def test_f9_marker_split_across_chunks():
    s = _VoiceMarkdownStripper()
    out = s.feed("Services:\n") + s.feed("1.") + s.feed(" Lashes\n2.") + s.feed(" Facial")
    assert "1." not in out and "2." not in out and "Lashes" in out and "Facial" in out


@pytest.mark.asyncio
async def test_f9_voice_stream_has_no_markdown():
    captured = []
    svc = _service(captured, text="Here:\n1. **Lashes**\n2. Facial")
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value={"chunks": []})):
        events = await _run(svc, "tell me something", "z13-f9", "voice")
    spoken = "".join(e["data"] for e in events if e["type"] == "token")
    assert "**" not in spoken and "1." not in spoken
    assert "**" not in next(e for e in events if e["type"] == "done")["answer"]


@pytest.mark.asyncio
async def test_f10_bare_latin_token_keeps_sticky_language():
    captured = []
    svc = _service(captured)
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value={"chunks": []})):
        await _run(svc, "मलाई सेवाहरू बताउनुहोस्", "z13-f10", "voice")
        await _run(svc, "Lashes.", "z13-f10", "voice")
        await _run(svc, "I would like to know about the services you offer here please", "z13-f10", "voice")
    assert clinic_tools.get_sticky_language("z13-f10") == "en"  # full sentence may switch
    d0 = clinic_agent._LANGUAGE_DIRECTIVES["ne_devanagari"]
    assert d0 in captured[1]["messages"][0]["content"]


def test_signal_regexes_untouched_by_z13():
    """Exit test 13 depends on the three s72 words staying OUT of the regexes."""
    for word in ("गर्दिनुहुन्न", "खुल्ला", "बारेमा"):
        assert not clinic_agent._BOOKING_SIGNAL.search(word)
        assert not clinic_agent._AVAILABILITY_SIGNAL.search(word)
