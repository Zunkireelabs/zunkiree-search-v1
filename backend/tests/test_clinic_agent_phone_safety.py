"""
CLINIC-PHONE-HALLUCINATION-BRIEF: the clinic agent must never surface a phone
number that didn't come from config.contact_phone or a search_knowledge chunk.

The underlying bug is non-deterministic (a different fabricated number each
run), so these tests assert over repeated runs rather than a single sample.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import ClinicAgentService, sanitize_phone_numbers

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


def _service_with_fabricated_reply(fabricated_number: str) -> ClinicAgentService:
    service = ClinicAgentService()
    reply = f"That sounds urgent — please call the clinic at {fabricated_number} right away."
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=lambda **kw: _stream(reply))
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


async def _run(service: ClinicAgentService, config: WidgetConfig | None):
    customer = _make_customer()
    events = []
    async for event in service.process_agent_stream(
        db=AsyncMock(),
        site_id="dental-city",
        session_id="s1",
        question="मेरो दाँत एकदम दुख्यो र सुन्निएको छ, कहाँ फोन गर्ने?",
        customer_id=customer.id,
        customer=customer,
        config=config,
        brand_name="Dental City",
    ):
        events.append(event)
    return events


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
