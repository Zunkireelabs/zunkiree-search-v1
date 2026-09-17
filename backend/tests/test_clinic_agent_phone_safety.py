"""
CLINIC-PHONE-HALLUCINATION-BRIEF: the clinic agent must never surface a phone
number that didn't come from config.contact_phone or a search_knowledge chunk.

The underlying bug is non-deterministic (a different fabricated number each
run), so these tests assert over repeated runs rather than a single sample.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import ClinicAgentService, sanitize_phone_numbers, _safe_flush_index

REAL_NUMBER = "980-1222339"
REAL_DIGITS = "9801222339"

# A sample of numbers the model has actually fabricated in the wild
# (Devanagari and Latin digits), per the brief.
FABRICATED_NUMBERS = [
    "०१-५५५५५५५",
    "०१-४२१२३४५",
    "01-1234567",
    "०१-४४४४४४४",
    "9841234599",
]


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


async def _stream_char_by_char(text: str):
    """Simulate real OpenAI streaming, where a delta can be a single character —
    the shape that made a per-delta sanitize impossible in the first place."""
    for ch in text:
        yield _chunk(content=ch)


def _service_with_reply(reply: str, char_by_char: bool = False) -> ClinicAgentService:
    service = ClinicAgentService()
    stream_fn = _stream_char_by_char if char_by_char else _stream
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=lambda **kw: stream_fn(reply))
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


def _service_with_fabricated_reply(fabricated_number: str) -> ClinicAgentService:
    reply = f"That sounds urgent — please call the clinic at {fabricated_number} right away."
    return _service_with_reply(reply)


async def _run(
    service: ClinicAgentService,
    config: WidgetConfig | None,
    question: str = "मेरो दाँत एकदम दुख्यो र सुन्निएको छ, कहाँ फोन गर्ने?",
    channel: str = "chat",
):
    customer = _make_customer()
    events = []
    async for event in service.process_agent_stream(
        db=AsyncMock(),
        site_id="dental-city",
        session_id="s1",
        question=question,
        customer_id=customer.id,
        customer=customer,
        config=config,
        brand_name="Dental City",
        channel=channel,
    ):
        events.append(event)
    return events


def _service_capturing_prompts(reply: str) -> tuple[ClinicAgentService, list]:
    """Like _service_with_reply, but also records every `messages` list
    passed to the (mocked) chat completion call, so a test can assert on the
    system prompt actually sent for a given channel."""
    captured_calls: list = []
    service = ClinicAgentService()

    def _create(**kw):
        captured_calls.append(kw["messages"])
        return _stream(reply)

    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service, captured_calls


# --- Unit tests: the sanitizer itself ---

@pytest.mark.parametrize("fabricated", FABRICATED_NUMBERS)
def test_sanitizer_strips_unknown_phone_numbers(fabricated):
    text = f"Please call the clinic at {fabricated} right away."
    sanitized = sanitize_phone_numbers(text, allowed_digits={REAL_DIGITS})
    assert fabricated not in sanitized
    for digit_run in ("5555555", "4212345", "1234567", "4444444"):
        assert digit_run not in sanitized.translate(str.maketrans("०१२३४५६७८९", "0123456789"))


def test_sanitizer_keeps_allowed_number():
    text = f"Please call the clinic at {REAL_NUMBER} right away."
    sanitized = sanitize_phone_numbers(text, allowed_digits={REAL_DIGITS})
    assert REAL_NUMBER in sanitized


def test_sanitizer_fails_closed_with_no_allowed_numbers():
    text = "Please call the clinic at 01-1234567 right away."
    sanitized = sanitize_phone_numbers(text, allowed_digits=set())
    assert "1234567" not in sanitized


def test_sanitizer_does_not_touch_dates_or_times():
    text = "We're open 2026-09-17 from 09:00 to 17:00."
    sanitized = sanitize_phone_numbers(text, allowed_digits=set())
    assert sanitized == text


def test_sanitizer_does_not_touch_price_ranges():
    text = "Cleaning costs NPR 1500-3000 depending on the case."
    sanitized = sanitize_phone_numbers(text, allowed_digits=set())
    assert sanitized == text


# --- F1 (PR #53 review): the visitor's own number must never be stripped ---

def test_sanitizer_keeps_visitor_supplied_number_when_marked_allowed():
    text = "I've prepared your booking for Sadin on 2026-09-28 at 10:00 AM. Phone: 9841540343. Shall I book this?"
    sanitized = sanitize_phone_numbers(text, allowed_digits={"9841540343"})
    assert "9841540343" in sanitized
    assert sanitized == text


@pytest.mark.asyncio
async def test_booking_readback_preserves_number_visitor_just_gave():
    """The booking flow's own verification step ('read it back, ask Shall I
    book this?') must not eat the visitor's number — they need to see it to
    catch a typo."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    reply = "Got it — I have your number as 9812345678. Shall I book this?"
    service = _service_with_reply(reply)

    events = await _run(service, config, question="My phone is 9812345678")
    done_event = next(e for e in events if e["type"] == "done")

    assert "9812345678" in done_event["answer"]


# --- F2 (PR #53 review): formatting must not defeat the guard ---

BYPASS_FORMATS = [
    "+977-1-4444444",
    "+977 1 4444444",
    "977014444444",
    "(01) 4444444",
    "01.4444444",
]


@pytest.mark.parametrize("fabricated", BYPASS_FORMATS)
def test_sanitizer_normalizes_formatting_before_comparing(fabricated):
    text = f"Call {fabricated} for urgent care."
    sanitized = sanitize_phone_numbers(text, allowed_digits={REAL_DIGITS})
    assert "4444444" not in sanitized.translate(str.maketrans("०१२३४५६७८९", "0123456789"))


@pytest.mark.parametrize("equivalent_format", [
    "980-1222339",
    "+977-980-1222339",
    "9779801222339",
])
def test_sanitizer_recognizes_same_number_in_different_formats(equivalent_format):
    text = f"Please call the clinic at {equivalent_format} right away."
    sanitized = sanitize_phone_numbers(text, allowed_digits={REAL_DIGITS})
    assert equivalent_format in sanitized


# --- F3 (PR #53 review): hold-back streaming must stay safe under real, ---
# --- character-granular deltas, not just the single-chunk mock above.    ---

@pytest.mark.asyncio
async def test_char_by_char_stream_never_leaks_fabricated_number_in_any_token():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    reply = "That sounds urgent — please call the clinic at +977-1-4444444 right away."
    service = _service_with_reply(reply, char_by_char=True)

    events = await _run(service, config)
    token_events = [e for e in events if e["type"] == "token"]
    done_event = next(e for e in events if e["type"] == "done")

    assert len(token_events) > 1, "hold-back streaming should still emit progressive chunks"
    for e in token_events:
        assert "4444444" not in e["data"]
    assert "4444444" not in done_event["answer"]


@pytest.mark.asyncio
async def test_char_by_char_stream_still_delivers_real_number():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    reply = f"That sounds urgent — please call the clinic at {REAL_NUMBER} right away."
    service = _service_with_reply(reply, char_by_char=True)

    events = await _run(service, config)
    done_event = next(e for e in events if e["type"] == "done")

    assert REAL_NUMBER in done_event["answer"]


# --- Integration: process_agent_stream over repeated fabrication runs ---

@pytest.mark.asyncio
@pytest.mark.parametrize("fabricated", FABRICATED_NUMBERS)
async def test_escalation_never_leaks_fabricated_number(fabricated):
    """Repeated-run non-determinism guard: whatever the model fabricates,
    the delivered answer must contain either the real number or no number."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    service = _service_with_fabricated_reply(fabricated)

    events = await _run(service, config)

    done_event = next(e for e in events if e["type"] == "done")
    token_events = [e for e in events if e["type"] == "token"]

    assert fabricated not in done_event["answer"]
    for e in token_events:
        assert fabricated not in e["data"]


@pytest.mark.asyncio
async def test_escalation_with_no_configured_phone_gives_no_digits():
    """FAIL CLOSED: unset contact_phone + no search_knowledge number => no digits at all."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    service = _service_with_fabricated_reply("01-1234567")

    events = await _run(service, config)
    done_event = next(e for e in events if e["type"] == "done")

    assert "1234567" not in done_event["answer"]


# --- N1 (PR #53 review pass 2): a booking reference is grounded like a phone ---
# --- number and must survive the confirm_booking read-back.                  ---

def _tool_call_chunk(call_id: str, name: str, arguments: str):
    delta = SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(index=0, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))],
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


async def _stream_tool_call(call_id: str, name: str, arguments: str):
    yield _tool_call_chunk(call_id, name, arguments)


@pytest.mark.asyncio
async def test_booking_reference_survives_confirm_booking_readback():
    """N1: booking_number is phone-shaped (7-13 digits) and would otherwise be
    stripped by the sanitizer as an unrecognized number ('Your booking
    reference is BK-, please keep it.')."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    service = ClinicAgentService()
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None

    responses = [
        _stream_tool_call("call_1", "confirm_booking", "{}"),
        _stream("Your booking reference is BK-20260928-0001, please keep it."),
    ]
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=lambda **kw: responses.pop(0))

    fake_result = {
        "booking": {
            "booking_number": "BK-20260928-0001",
            "date": "2026-09-28",
            "start_time": "10:00",
            "treatment_name": "General Dentistry",
            "branch_name": "Main Branch",
        }
    }
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=fake_result)):
        events = await _run(service, config)

    done_event = next(e for e in events if e["type"] == "done")
    assert "BK-20260928-0001" in done_event["answer"]


# --- N2 (PR #53 review pass 2): the streaming boundary must not cut through ---
# --- an in-progress digit run, leaving the widget out of sync with `done`.  ---

def test_safe_flush_index_pulls_back_before_in_progress_digit_run():
    text = "Please call us at +977 1"
    boundary = _safe_flush_index(text, hold_back_tokens=2)
    assert boundary <= text.index("+977")


def test_safe_flush_index_unaffected_when_tail_has_no_digits():
    text = "Please call us at the clinic today"
    boundary = _safe_flush_index(text, hold_back_tokens=2)
    assert text[:boundary] == "Please call us at the clinic"


@pytest.mark.asyncio
async def test_char_by_char_stream_does_not_leak_digit_run_split_by_spaces():
    """A fabricated number spread across separate whitespace tokens
    ("+977 1 4444444") must not leak piecemeal just because no single flush
    window ever contains all 7+ digits at once — and what the visitor saw
    while streaming must match what `done` / conversation history keep."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    reply = "Please call us at +977 1 4444444 for urgent care today."
    service = _service_with_reply(reply, char_by_char=True)

    events = await _run(service, config)
    token_events = [e for e in events if e["type"] == "token"]
    done_event = next(e for e in events if e["type"] == "done")

    streamed = "".join(e["data"] for e in token_events)
    assert "4444444" not in streamed.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    assert streamed == done_event["answer"]


# --- VOICE-CHANNEL-RESPONSE-BRIEF §4: channel is a pure adapter declaration ---
# --- that selects a response-shape profile in the one agent definition.     ---

@pytest.mark.asyncio
async def test_voice_channel_prompt_carries_budget_and_safety_exemptions():
    """The `channel: "voice"` declaration must reach the system prompt with
    a directive one/two-sentence budget and both safety exemptions
    (escalations, phone number) — repeated so a flaky mock ordering can't
    hide a wiring bug."""
    for _ in range(3):
        service, captured = _service_capturing_prompts("Sure, we're open 9-5.")
        await _run(service, config=None, channel="voice")

        assert len(captured) == 1
        system_prompt = captured[0][0]["content"]
        assert "VOICE:" in system_prompt
        assert "ONE short sentence" in system_prompt
        assert "80 characters" in system_prompt
        assert "never shortened" in system_prompt
        # The block must sit at the END of the prompt (most salient
        # position) — see VOICE-PROFILE-STRENGTHEN-BRIEF §3.
        assert system_prompt.rstrip().endswith(
            "phone number whenever you tell someone to call."
        )


@pytest.mark.asyncio
async def test_chat_channel_omits_voice_block():
    """Default channel ("chat") must not carry any voice-only instructions —
    the adapter declaring nothing must behave exactly as before this brief."""
    service, captured = _service_capturing_prompts("Sure, we're open 9-5.")
    await _run(service, config=None, channel="chat")

    system_prompt = captured[0][0]["content"]
    assert "VOICE:" not in system_prompt


@pytest.mark.asyncio
async def test_voice_channel_does_not_change_phone_sanitization():
    """The channel only changes response shape, never the phone-number
    safety net — a fabricated number must still be stripped under voice."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    service = _service_with_fabricated_reply("01-1234567")

    events = await _run(service, config, channel="voice")
    done_event = next(e for e in events if e["type"] == "done")

    assert "1234567" not in done_event["answer"]


# --- Phone-presence follow-up (post-#53 smoke): "never wrong" must also be ---
# --- "always present" whenever config.contact_phone is set on escalation.  ---

@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["chat", "voice"])
async def test_medical_prompt_mandates_stating_the_number_when_verified(channel):
    """Prompt-content guard, repeated over both channels: the MEDICAL section
    must instruct the model to ALWAYS give the verified number on escalation,
    not merely permit it — the earlier wording ('only state ... if it
    appears') was satisfied by omitting the number entirely, which is how 2
    of 6 live escalation probes on stage came back with no number at all."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=REAL_NUMBER)
    service, captured = _service_capturing_prompts("Please call us right away.")

    await _run(service, config, channel=channel)

    system_prompt = captured[0][0]["content"]
    assert REAL_NUMBER in system_prompt
    assert "ALWAYS tell them to call the clinic immediately AND" in system_prompt
    assert "state the clinic's verified phone number" in system_prompt


@pytest.mark.asyncio
async def test_medical_prompt_still_forbids_digits_when_unverified():
    """The mandate to always state the number only applies once one is
    verified — with none configured, the prompt must keep forbidding digits
    outright rather than accidentally demanding a number that doesn't exist."""
    service, captured = _service_capturing_prompts("Please call us right away.")

    await _run(service, config=None, channel="chat")

    system_prompt = captured[0][0]["content"]
    assert "WITHOUT stating any digits" in system_prompt


# --- ZUNKIREE-CLEANUP-BRIEF C2: false refusal + language matching, Nepali-only ---

@pytest.mark.asyncio
async def test_prompt_scopes_facts_to_clinic_data_not_agent_process():
    """FACTS must not read as covering the agent's own capabilities/process —
    that over-broad scope is what made the model prepend a false refusal
    ('I can't explain the booking process...') before answering from BOOKING
    in Nepali. The prompt must say explicitly that describing how booking
    works, unlike clinic data, needs no tool and no refusal."""
    service, captured = _service_capturing_prompts("Sure, here's how booking works.")
    await _run(service, config=None, channel="chat")

    system_prompt = captured[0][0]["content"]
    assert "FACTS:" in system_prompt
    assert "clinic DATA only" in system_prompt
    assert "own capabilities" in system_prompt
    assert "without a tool and without any disclaimer or refusal" in system_prompt


@pytest.mark.asyncio
async def test_prompt_carries_explicit_language_matching_rule():
    """The system prompt is English-only text but must explicitly instruct
    the model to reply in the visitor's own language and to keep every other
    rule (FACTS, BOOKING) in force regardless of language — the earlier
    prompt had no LANGUAGE rule at all, which is the same root cause as the
    Nepali-only false refusal (REVIEW-PR55 §4.3)."""
    service, captured = _service_capturing_prompts("Sure, we're open 9-5.")
    await _run(service, config=None, channel="chat")

    system_prompt = captured[0][0]["content"]
    assert "LANGUAGE:" in system_prompt
    assert "English in, English out" in system_prompt
    assert "applies identically no matter which language" in system_prompt
