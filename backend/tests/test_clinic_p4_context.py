"""
P4-VOICE-SAFETY-GUARDS-BRIEF Part B: Orca's tenant context (B1) and the
medical-escalation exemption from voice-length limits (B2).
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import (
    ClinicAgentService,
    is_medical_escalation_question,
    resolve_handoff_available,
    sanitize_phone_numbers,
    _extract_phone_digits,
)

REAL = "980-1222339"
HANDOFF = "+977-1-4441234"


def _customer():
    return Customer(id=uuid.uuid4(), name="Dental City", site_id="dental-city",
                    api_key="k", website_type="clinic")


def _config():
    return WidgetConfig(customer_id=uuid.uuid4(), contact_phone=REAL)


def _chunk(content=None, finish=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=content, tool_calls=None), finish_reason=finish)])


def _service(reply, finish=None):
    calls = []

    async def _stream():
        yield _chunk(reply, finish)

    svc = ClinicAgentService()

    def _create(**kw):
        calls.append(kw)
        return _stream()

    svc.client = AsyncMock()
    svc.client.chat.completions.create = AsyncMock(side_effect=_create)
    svc.conversation_store = AsyncMock()
    svc.conversation_store.get_messages = lambda sid: []
    svc.conversation_store.add_message = lambda *a, **k: None
    return svc, calls


async def _run(svc, question="What are your hours?", channel="voice", **ctx):
    c = _customer()
    out = []
    async for e in svc.process_agent_stream(
        db=AsyncMock(), site_id="dental-city", session_id=str(uuid.uuid4()),
        question=question, customer_id=c.id, customer=c, config=_config(),
        brand_name="Dental City", channel=channel, **ctx,
    ):
        out.append(e)
    return out


def _text(events):
    return "".join(e["data"] for e in events if e["type"] == "token")


def test_resolve_handoff_available_defaults():
    assert resolve_handoff_available(None, None, False) is True      # fields absent
    assert resolve_handoff_available(True, HANDOFF, True) is True
    assert resolve_handoff_available(False, HANDOFF, True) is False  # closed
    assert resolve_handoff_available(True, None, True) is False      # explicit null
    assert resolve_handoff_available(True, "  ", True) is False       # blank


@pytest.mark.asyncio
async def test_absent_fields_leave_prompt_unchanged():
    svc, calls = _service("We open at nine.")
    await _run(svc)
    assert "AVAILABILITY" not in calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_closed_channel_states_facts_and_forbids_transfer():
    svc, calls = _service("We're closed today.")
    await _run(svc, channel_open=False, closed_reason="closed_date",
               handoff_target=HANDOFF, handoff_target_sent=True)
    p = calls[0]["messages"][0]["content"]
    assert "currently closed (closed_date)" in p
    assert "never offer to transfer" in p


@pytest.mark.asyncio
async def test_empty_handoff_target_forbids_transfer_even_when_open():
    svc, calls = _service("Sure.")
    await _run(svc, channel_open=True, handoff_target="", handoff_target_sent=True)
    p = calls[0]["messages"][0]["content"]
    assert "never offer to transfer" in p
    assert "currently closed" not in p


@pytest.mark.asyncio
async def test_transfer_offer_while_unavailable_is_logged(caplog):
    svc, _ = _service("One moment, I'll transfer you to the front desk.")
    with caplog.at_level("WARNING", logger="zunkiree.clinic_agent"):
        await _run(svc, channel_open=False, handoff_target_sent=True)
    assert any("handoff_offered_unavailable" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_transfer_offer_while_available_not_logged(caplog):
    svc, _ = _service("One moment, I'll transfer you to the front desk.")
    with caplog.at_level("WARNING", logger="zunkiree.clinic_agent"):
        await _run(svc, channel_open=True, handoff_target=HANDOFF, handoff_target_sent=True)
    assert not any("handoff_offered_unavailable" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_handoff_number_is_allowed_not_stripped():
    svc, _ = _service(f"Please call {HANDOFF} now.")
    events = await _run(svc, channel_open=True, handoff_target=HANDOFF, handoff_target_sent=True)
    assert "4441234" in _text(events)


@pytest.mark.asyncio
async def test_handoff_number_stripped_when_not_sent():
    svc, _ = _service(f"Please call {HANDOFF} now.")
    events = await _run(svc)
    assert "4441234" not in _text(events)


def test_non_number_handoff_target_adds_no_digits():
    assert _extract_phone_digits("sip:reception@clinic.example") == set()


@pytest.mark.asyncio
async def test_spoken_brand_name_used_on_voice_only():
    svc, calls = _service("Hi.")
    await _run(svc, channel="voice", spoken_brand_name="Dental Siti")
    assert "Dental Siti's front-desk" in calls[0]["messages"][0]["content"]
    svc, calls = _service("Hi.")
    await _run(svc, channel="chat", spoken_brand_name="Dental Siti")
    assert "Dental City's front-desk" in calls[0]["messages"][0]["content"]


# ---- B2 ----

@pytest.mark.parametrize("q", [
    "I have severe pain and my face is swollen",
    "my gum is bleeding a lot",
    "मेरो दाँत एकदम दुख्यो र सुन्निएको छ, कहाँ फोन गर्ने?",
    "मेरो गिजाबाट धेरै रगत बगिरहेको छ।",
    "mero daath dukhirako cha",
])
def test_escalation_questions_detected(q):
    assert is_medical_escalation_question(q)


@pytest.mark.parametrize("q", ["What are your hours?", "painless whitening price?", "तपाईंहरूको समय कति हो?", ""])
def test_ordinary_questions_not_escalation(q):
    assert not is_medical_escalation_question(q)


@pytest.mark.asyncio
async def test_voice_escalation_drops_length_block_and_raises_cap():
    svc, calls = _service("Call now.")
    await _run(svc, question="I have severe pain and swelling")
    p = calls[0]["messages"][0]["content"]
    assert "under 80 characters" not in p
    assert "No length limit applies" in p
    assert calls[0]["max_tokens"] == 700


@pytest.mark.asyncio
async def test_voice_ordinary_keeps_length_block_and_cap():
    svc, calls = _service("Nine to five.")
    await _run(svc, question="What are your hours?")
    p = calls[0]["messages"][0]["content"]
    assert "under 80 characters" in p
    assert calls[0]["max_tokens"] == 350


@pytest.mark.asyncio
async def test_chat_escalation_unchanged():
    svc, calls = _service("Call now.")
    await _run(svc, question="I have severe pain", channel="chat")
    assert "VOICE:" not in calls[0]["messages"][0]["content"]
    assert calls[0]["max_tokens"] == 350


@pytest.mark.asyncio
async def test_truncated_answer_is_logged(caplog):
    svc, _ = _service("Call the clinic at", finish="length")
    with caplog.at_level("WARNING", logger="zunkiree.clinic_agent"):
        await _run(svc, question="severe pain")
    assert any("answer_truncated" in r.message and "escalation_turn=True" in r.message
               for r in caplog.records)


# ---- endpoint wiring ----

@pytest.mark.asyncio
@pytest.mark.parametrize("payload,expect", [
    ({}, dict(channel_open=None, handoff_target=None, handoff_target_sent=False)),
    ({"channel_open": False, "closed_reason": "closed_date", "handoff_target": None},
     dict(channel_open=False, handoff_target=None, handoff_target_sent=True)),
    ({"channel_open": True, "handoff_target": HANDOFF, "spoken_brand_name": "Dental Siti"},
     dict(channel_open=True, handoff_target=HANDOFF, handoff_target_sent=True)),
])
async def test_stream_endpoint_forwards_orca_context(payload, expect):
    from app.api.query import QueryRequest, submit_query_stream
    from unittest.mock import patch

    customer = _customer()
    seen = {}

    async def gen(*a, **kw):
        seen.update(kw)
        yield {"type": "done", "answer": "x", "suggestions": [], "sources": []}

    clinic = AsyncMock()
    clinic.process_agent_stream = gen
    request = AsyncMock()
    request.headers = {}
    request.client = None
    query = QueryRequest(site_id="s", question="What services do you offer?", session_id=None, channel="voice", **payload)
    with patch("app.api.query.get_query_service") as gq, \
         patch("app.services.clinic_agent.get_clinic_agent_service", return_value=clinic):
        gq.return_value._get_customer = AsyncMock(return_value=customer)
        gq.return_value._get_widget_config = AsyncMock(return_value=_config())
        resp = await submit_query_stream(request, query, db=AsyncMock())
        body = "".join([c async for c in resp.body_iterator])
    assert seen, body
    for k, v in expect.items():
        assert seen[k] == v
