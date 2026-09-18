"""
CLINIC-ESCALATION-LANGUAGE-BRIEF: a medical escalation must be answered in the
visitor's own language — a correct phone number in the wrong language is a
failed escalation. Covers the per-turn language directive (approach A) and the
escalation-only Devanagari safety net (approach B).
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import ClinicAgentService

REAL_NUMBER = "980-1222339"


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000cc"),
        name="Dental City",
        site_id="dental-city",
        api_key="key",
        website_type="clinic",
    )


def _chunk(content=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None))])


async def _stream(text: str):
    yield _chunk(content=text)


def _completion(text: str):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


async def _run(service, config, question, channel="chat", session_id="s1"):
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
        channel=channel,
    ):
        events.append(event)
    return events


def _service_with_streamed_and_translated(streamed_reply: str, translated_reply: str) -> ClinicAgentService:
    """Mocks the main streaming call and the non-streaming translation call
    distinctly, keyed on the `stream` kwarg the two call sites pass."""
    service = ClinicAgentService()

    def _create(**kw):
        if kw.get("stream"):
            return _stream(streamed_reply)
        return _completion(translated_reply)

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


@pytest.mark.asyncio
async def test_language_directive_reflects_detected_language():
    """Approach A: the system prompt gets a per-turn directive naming the
    detected language, not just the generic standing LANGUAGE rule."""
    service = ClinicAgentService()
    captured: list = []

    def _create(**kw):
        captured.append(kw["messages"])
        return _stream("ठिक छ")

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None

    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    await _run(service, config, question="तपाईंको क्लिनिक कहिले खुल्छ?")

    system_prompt = captured[0][0]["content"]
    assert "LANGUAGE-THIS-TURN: The visitor wrote in Devanagari Nepali." in system_prompt


@pytest.mark.asyncio
async def test_devanagari_escalation_answered_in_english_gets_translated():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    english_reply = f"Please call the clinic immediately at {REAL_NUMBER} for urgent assistance."
    devanagari_reply = f"कृपया तुरुन्तै क्लिनिकलाई {REAL_NUMBER} मा सम्पर्क गर्नुहोस्।"
    service = _service_with_streamed_and_translated(english_reply, devanagari_reply)

    events = await _run(service, config, question="मेरो गिजाबाट धेरै रगत बगिरहेको छ।")
    done_event = next(e for e in events if e["type"] == "done")

    assert done_event["answer"] == devanagari_reply
    assert REAL_NUMBER in done_event["answer"]


@pytest.mark.asyncio
async def test_devanagari_non_escalation_reply_not_translated():
    """The safety net is escalation-only — an ordinary Devanagari-input answer
    that comes back in English (no phone number) is left to approach A (the
    per-turn directive), not retranslated code-side."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    english_reply = "We are open every day from 10 AM to 8 PM."
    service = _service_with_streamed_and_translated(english_reply, "SHOULD NOT BE CALLED")

    events = await _run(service, config, question="तपाईंको क्लिनिक कहिले खुल्छ?")
    done_event = next(e for e in events if e["type"] == "done")

    assert done_event["answer"] == english_reply
    assert service.client.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_romanized_and_english_escalations_not_run_through_translation_net():
    """Approach B is scoped to Devanagari input specifically — a script-based
    mismatch check can't reliably tell romanized Nepali from English, so those
    are left entirely to approach A."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    english_reply = f"Please call the clinic immediately at {REAL_NUMBER} for urgent assistance."
    service = _service_with_streamed_and_translated(english_reply, "SHOULD NOT BE CALLED")

    events = await _run(service, config, question="Mero gijabata dherai ragat bagirako cha.")
    done_event = next(e for e in events if e["type"] == "done")

    assert done_event["answer"] == english_reply
    assert service.client.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_translated_answer_is_resanitized_against_stray_digits():
    """Ordering hazard from the brief: the translation pass runs after the
    first sanitize and could reformat or invent digits (e.g. Devanagari
    numerals the allow-list wouldn't recognize, or an outright wrong number).
    The result must be re-sanitized rather than trusted."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    english_reply = f"Please call the clinic immediately at {REAL_NUMBER} for urgent assistance."
    bad_translation = "कृपया तुरुन्तै क्लिनिकलाई ०१-९९९९९९९ मा सम्पर्क गर्नुहोस्।"
    service = _service_with_streamed_and_translated(english_reply, bad_translation)

    events = await _run(service, config, question="मेरो अनुहार सुन्निएको छ र धेरै दुखिरहेको छ।")
    done_event = next(e for e in events if e["type"] == "done")

    assert "९९९९९९९" not in done_event["answer"]
