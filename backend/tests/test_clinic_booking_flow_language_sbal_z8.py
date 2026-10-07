"""
SBAL Z8 regression (brief: docs/orca-platform/sbal/SBAL-Z8-BOOKING-FLOW-LANGUAGE-BRIEF.md):

Prod lane evidence — tapping a slot chip sent prepare_booking with no
name/phone, which failed, and the reply was a false English "I can book..."
+ the same slot chips shown again. Addendum: repeating this with a SECOND,
different slot chip (12:30, then 10:30, then 10:30 again) looped forever —
never asking for the missing name/phone, never progressing.

Root cause (bisected 0b59b7f8..453063e1, where the 10-06 IG booking on
0b59b7f8 completed but the same flow now loops): bedf258 ("SBAL-Z3 B1")
force-calls check_availability on iteration 1 whenever the turn's text
names a time/date — which every slot-chip payload does ("Book X on D at
T"). That inserts a redundant same-slot re-check between the chip tap and
prepare_booking that didn't exist at 0b59b7f8, and empirically changes the
model's next move: it calls prepare_booking optimistically, without ever
asking for name/phone, then (on the resulting INVALID_NAME/INVALID_PHONE
error) narrates a false "I can book..." instead of asking — the same
llm_prompt_mandate_vs_actual_behavior pattern documented elsewhere in this
file. B1 itself fixes a real, different bug (answering availability
questions from memory) and is not reverted; this module's fix is the
deterministic, code-built ask added in clinic_agent.py (no longer
dependent on the model noticing and asking on its own), which is backend-
agnostic (works identically for every tenant/backend_type) and channel-
agnostic (every non-voice channel).

Scripted as a single multi-turn conversation per language, with
execute_clinic_tool mocked (this flow doesn't branch on backend_type —
clinic_tools.py's _prepare_booking is tested directly against both
clinicmd and zennly in test_clinic_tools.py).
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import ClinicAgentService
from app.services.clinic_tools import reset_session_state


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-00000000005a"),
        name="SBAL — Sami Brows and Lashes",
        site_id="sbal",
        api_key="key",
        website_type="clinic",
    )


def _chunk(content=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None))])


async def _stream(text: str):
    yield _chunk(content=text)


def _tool_call_chunk(call_id: str, name: str, arguments: str):
    delta = SimpleNamespace(
        content=None,
        tool_calls=[SimpleNamespace(index=0, id=call_id, function=SimpleNamespace(name=name, arguments=arguments))],
    )
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


async def _stream_tool_call(call_id: str, name: str, arguments: str):
    yield _tool_call_chunk(call_id, name, arguments)


def _service_for_responses(responses: list) -> ClinicAgentService:
    service = ClinicAgentService()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=lambda **kw: responses.pop(0))
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


async def _run(service: ClinicAgentService, config, question: str, session_id: str, channel: str = "instagram") -> list:
    customer = _make_customer()
    events = []
    async for event in service.process_agent_stream(
        db=AsyncMock(),
        site_id="sbal",
        session_id=session_id,
        question=question,
        customer_id=customer.id,
        customer=customer,
        config=config,
        brand_name="SBAL",
        channel=channel,
    ):
        events.append(event)
    return events


def _tool_exec_side_effect(**kwargs):
    tool_name = kwargs["tool_name"]
    tool_args = kwargs["tool_args"]
    if tool_name == "check_availability":
        return {
            "service": {"name": "Brow Lamination"},
            "date": "2026-10-08",
            "open_times": ["12:30", "10:30"],
        }
    if tool_name == "prepare_booking":
        if not tool_args.get("full_name") or not tool_args.get("phone"):
            return {
                "error": "INVALID_PHONE" if not tool_args.get("phone") else "INVALID_NAME",
                "message": "missing visitor details",
                "service_name": "Brow Lamination",
                "date": "2026-10-08",
                "time": tool_args.get("time", ""),
            }
        return {
            "summary": "Brow Lamination on Thursday, 2026-10-08 at 10:30 for Test Demo (+9779800000000) at Main Branch.",
            "pending_booking": {
                "service_name": "Brow Lamination", "date": "2026-10-08", "time": "10:30",
                "full_name": "Test Demo", "phone_e164": "+9779800000000", "branch_name": "Main Branch",
            },
        }
    raise AssertionError(f"unexpected tool call: {tool_name}")


@pytest.fixture(autouse=True)
def _reset(request):
    yield
    # Best-effort; each test uses a fresh uuid4 session_id so this mostly
    # guards against a future test reusing a literal id.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "language,availability_question,missing_details_fragment",
    [
        ("en", "Are you free tomorrow for a brow lamination?", "What's your full name and phone number?"),
        ("ne_romanized", "Brow lamination ko lagi bholi khali time cha?", "naam ra phone number"),
    ],
)
async def test_slot_pick_asks_for_missing_details_never_reoffers_slots_twice(
    language, availability_question, missing_details_fragment,
):
    """The full regression repro: availability -> pick a slot (fails,
    missing details) -> pick a DIFFERENT slot (fails again, missing
    details) -> give name+phone (succeeds, confirm step). Never once
    does `ui.slots` reappear after the first slot pick, and the agent
    never claims a booking that didn't happen."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None, service_cards=True)
    session_id = str(uuid.uuid4())
    reset_session_state(session_id)

    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_tool_exec_side_effect):
        # Turn 1: availability question -> check_availability -> slots shown.
        service = _service_for_responses([
            _stream_tool_call("c1", "check_availability", '{"service": "Brow Lamination", "date": "2026-10-08"}'),
            _stream("Here are the open times."),
        ])
        events = await _run(service, config, availability_question, session_id)
        done = next(e for e in events if e["type"] == "done")
        assert done.get("ui", {}).get("slots"), "turn 1 must offer slot chips"

        # Turn 2: tap the 12:30 chip (synthetic English payload regardless
        # of language) -> re-check + prepare_booking with no details ->
        # must ask for name/phone, never re-show slots.
        service = _service_for_responses([
            _stream_tool_call("c2", "check_availability", '{"service": "Brow Lamination", "date": "2026-10-08"}'),
            _stream_tool_call(
                "c3", "prepare_booking",
                '{"service": "Brow Lamination", "date": "2026-10-08", "time": "12:30"}',
            ),
        ])
        events = await _run(service, config, "Book Brow Lamination on 2026-10-08 at 12:30", session_id)
        done = next(e for e in events if e["type"] == "done")
        assert "ui" not in done or not done["ui"].get("slots"), "must not re-offer slot chips after a pick"
        assert missing_details_fragment in done["answer"]
        assert "I can book" not in done["answer"]

        # Turn 3 (the addendum repro): tap a DIFFERENT slot (10:30) without
        # ever having given name/phone — must fail the same honest way,
        # not loop with slot chips again.
        service = _service_for_responses([
            _stream_tool_call("c4", "check_availability", '{"service": "Brow Lamination", "date": "2026-10-08"}'),
            _stream_tool_call(
                "c5", "prepare_booking",
                '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30"}',
            ),
        ])
        events = await _run(service, config, "Book Brow Lamination on 2026-10-08 at 10:30", session_id)
        done = next(e for e in events if e["type"] == "done")
        assert "ui" not in done or not done["ui"].get("slots"), "second pick must not re-offer slot chips either"
        assert missing_details_fragment in done["answer"]

        # Turn 4: visitor gives name + phone as real text -> prepare_booking
        # now succeeds -> confirm step (chips), never slot chips, and no
        # booking is made (confirm_booking is never called in this test).
        service = _service_for_responses([
            _stream_tool_call(
                "c6", "prepare_booking",
                '{"service": "Brow Lamination", "date": "2026-10-08", "time": "10:30", '
                '"full_name": "Test Demo", "phone": "9800000000"}',
            ),
        ])
        events = await _run(service, config, "Test Demo, 9800000000", session_id)
        done = next(e for e in events if e["type"] == "done")
        assert done.get("ui", {}).get("confirm")
        assert not done.get("ui", {}).get("slots")
        assert not any(e["type"] == "tool_call" and e["name"] == "confirm_booking" for e in events)

    reset_session_state(session_id)


@pytest.mark.asyncio
async def test_synthetic_chip_tap_does_not_flip_language_to_english():
    """SBAL-Z8 F2: a Nepali availability question establishes the sticky
    session language; the chip tap's code-synthesized ENGLISH payload text
    must not flip the reply language even though its own words are
    English."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None, service_cards=True)
    session_id = str(uuid.uuid4())
    reset_session_state(session_id)

    with patch("app.services.clinic_agent.execute_clinic_tool", side_effect=_tool_exec_side_effect):
        service = _service_for_responses([
            _stream_tool_call("c1", "check_availability", '{"service": "Brow Lamination", "date": "2026-10-08"}'),
            _stream("Yo samaya haru khali cha."),
        ])
        await _run(service, config, "Brow lamination ko lagi bholi khali time cha?", session_id)

        service = _service_for_responses([
            _stream_tool_call("c2", "check_availability", '{"service": "Brow Lamination", "date": "2026-10-08"}'),
            _stream_tool_call(
                "c3", "prepare_booking",
                '{"service": "Brow Lamination", "date": "2026-10-08", "time": "12:30"}',
            ),
        ])
        events = await _run(service, config, "Book Brow Lamination on 2026-10-08 at 12:30", session_id)
        done = next(e for e in events if e["type"] == "done")
        assert "naam ra phone number" in done["answer"]
        assert "What's your full name" not in done["answer"]

    reset_session_state(session_id)
