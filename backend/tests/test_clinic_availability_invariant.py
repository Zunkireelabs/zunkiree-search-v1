"""
SBAL-Z3 B1: the 10-06 team IG test showed the agent answering availability
questions straight from its own guess (Hardik's lane log — every one of
those turns had `tools=[]`), contradicting an actual check_availability
result two turns later. A prompt rule won't hold here any more than
anywhere else in this file (llm_prompt_mandate_vs_actual_behavior) — this
is the code-side invariant: a turn that names a time/date, or asks whether
something is free/available, forces iteration 1's tool_choice to
check_availability, so the model can never give a final answer about
availability without a fresh check that same turn.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.widget_config import WidgetConfig
from app.services.clinic_agent import (
    ClinicAgentService,
    _AVAILABILITY_SIGNAL,
    _mentions_time_or_date,
)
from tests.test_clinic_booking_truth import _make_customer, _stream, _stream_tool_call

FORCED_CHOICE = {"type": "function", "function": {"name": "check_availability"}}


def _service_capturing_calls(responses: list, calls: list) -> ClinicAgentService:
    service = ClinicAgentService()
    service.client = AsyncMock()

    async def _create(**kw):
        calls.append(kw)
        return responses.pop(0)

    service.client.chat.completions.create = AsyncMock(side_effect=_create)
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


async def _run_turn(service: ClinicAgentService, config, question: str, session_id: str) -> list:
    customer = _make_customer()
    events = []
    async for event in service.process_agent_stream(
        db=AsyncMock(), site_id="sbal", session_id=session_id, question=question,
        customer_id=customer.id, customer=customer, config=config, brand_name="SBAL", channel="instagram",
    ):
        events.append(event)
    return events


async def fake_execute_clinic_tool(*, tool_name, tool_args=None, **kw):
    if tool_name == "check_availability":
        return {"service": {"id": "svc1", "name": "Lash Tint"}, "date": "2026-10-10", "open_times": ["10:30", "11:00"]}
    return {}


# --- Signal detection unit tests ---


@pytest.mark.parametrize("msg", [
    "Malai 11:30 am ko chaiyeko cha",
    "12 bajeko?",
    "11:30 ko cha tah khali?",
    "Is 2pm free?",
    "Do you have anything available tomorrow?",
    "खाली समय छ?",
])
def test_availability_signal_matches_time_or_free_question(msg):
    import datetime as dt
    now = dt.datetime(2026, 10, 10, 9, 0)
    assert _AVAILABILITY_SIGNAL.search(msg) or _mentions_time_or_date(msg, now)


@pytest.mark.parametrize("msg", [
    "What is SBAL?",
    "Who are your stylists?",
    "Thank you!",
])
def test_availability_signal_does_not_match_plain_questions(msg):
    import datetime as dt
    now = dt.datetime(2026, 10, 10, 9, 0)
    assert not (_AVAILABILITY_SIGNAL.search(msg) or _mentions_time_or_date(msg, now))


# --- Integration: forced tool_choice on the real turn sequence ---


@pytest.mark.asyncio
async def test_hardik_sequence_forces_check_availability_on_every_time_mention_turn():
    """Replays the 10-06 lane-log sequence (Hardik, SBAL-Z3 brief table).
    Turns 1, 2, 4, 5 each name a time and must force check_availability;
    turn 3 ("anything other than 10") already worked in the real incident
    and is included for sequence fidelity, not asserted on specifically.

    The real conversation had already named "Lash Tint" in turns before the
    ones the brief's table quotes (which starts mid-conversation at
    09:42:39) — seed that same resolved-service context via the date
    anchor (review on #117), so every quoted turn forces the SPECIFIC
    check_availability tool, matching the brief's own exit test ("every
    time-mention turn shows check_availability in turn_summary.tools")."""
    from app.services import clinic_agent as clinic_agent_module

    sid = f"t-{uuid.uuid4()}"
    clinic_agent_module._DATE_ANCHOR[sid] = "2026-10-10"
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    calls: list = []

    turns = [
        ("Malai 11:30 am ko chaiyeko cha", [
            _stream_tool_call("c1", "check_availability", '{"service": "Lash Tint", "date": "2026-10-10", "time": "11:30"}'),
            _stream("11:30 is not available on that date. Would you like 10:00 instead?"),
        ]),
        ("12 bajeko?", [
            _stream_tool_call("c2", "check_availability", '{"service": "Lash Tint", "date": "2026-10-10", "time": "12:00"}'),
            _stream("12:00 is not available either."),
        ]),
        ("Aru kunai time cha 10 vanda?", [
            _stream_tool_call("c3", "check_availability", '{"service": "Lash Tint", "date": "2026-10-10"}'),
            _stream("Other than 10, we have 10:30, 11:00, 11:30, 12:00, 12:30, 1:00 free."),
        ]),
        ("Agi 11:30 chaina vanu vako haina?", [
            _stream_tool_call("c4", "check_availability", '{"service": "Lash Tint", "date": "2026-10-10", "time": "11:30"}'),
            _stream("Checking again — 11:30 is in fact open. Want me to book it?"),
        ]),
        ("11:30 ko cha tah khali?", [
            _stream_tool_call("c5", "check_availability", '{"service": "Lash Tint", "date": "2026-10-10", "time": "11:30"}'),
            _stream("Yes, 11:30 is open — shall I book it?"),
        ]),
    ]

    turn_call_ranges: list[tuple[int, int]] = []
    try:
        with patch("app.services.clinic_agent.execute_clinic_tool", fake_execute_clinic_tool):
            for question, responses in turns:
                service = _service_capturing_calls(list(responses), calls)
                start = len(calls)
                await _run_turn(service, config, question, sid)
                turn_call_ranges.append((start, len(calls)))
    finally:
        clinic_agent_module._DATE_ANCHOR.pop(sid, None)

    assert len(turn_call_ranges) == 5

    # Turns 1, 2, 4, 5 (0-indexed 0,1,3,4): iteration 1 of that turn forced
    # check_availability — the brief's own acceptance test ("assert a tool
    # call on turns 1, 2, 4, 5").
    for idx in (0, 1, 3, 4):
        start, _ = turn_call_ranges[idx]
        assert calls[start]["tool_choice"] == FORCED_CHOICE, f"turn {idx + 1} did not force check_availability"


@pytest.mark.asyncio
async def test_non_availability_turn_unaffected_on_voice():
    """No regression on a turn that doesn't mention a time — tool_choice
    stays 'auto', same code path as before B1 (brief: "prove there's no
    latency regression on a turn that doesn't mention a time" on voice)."""
    sid = f"t-{uuid.uuid4()}"
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    calls: list = []
    responses = [_stream("We're a brow and lash salon — happy to help with anything you need.")]
    service = _service_capturing_calls(responses, calls)

    with patch("app.services.clinic_agent.execute_clinic_tool", fake_execute_clinic_tool):
        events = await _run_turn(service, config, "Tell me about SBAL", sid)

    assert calls[0]["tool_choice"] == "auto"
    done = next(e for e in events if e["type"] == "done")
    assert done["answer"]


@pytest.mark.asyncio
async def test_fresh_session_availability_question_never_forces_a_guessed_service():
    """Review on #117: forcing check_availability specifically would force
    the model to fill its required `service` argument — on a FRESH session
    with no service ever named, that means inventing one, breaking "never
    guess a service name". tool_choice must be the generic "required"
    (some tool, model's choice — e.g. list_services) instead."""
    sid = f"t-{uuid.uuid4()}"
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    calls: list = []
    responses = [
        _stream_tool_call("c1", "list_services", "{}"),
        _stream("We offer brow and lash services — which one were you thinking of, and for when?"),
    ]
    service = _service_capturing_calls(responses, calls)

    async def fake_list_services(*, tool_name, tool_args=None, **kw):
        assert tool_name == "list_services"
        return {"branch": {"id": "b1", "name": "Main Branch"}, "services": [{"id": "s1", "name": "Lash Lift"}]}

    with patch("app.services.clinic_agent.execute_clinic_tool", fake_list_services):
        events = await _run_turn(service, config, "Are you free tomorrow?", sid)

    assert calls[0]["tool_choice"] == "required"
    done = next(e for e in events if e["type"] == "done")
    assert done["answer"]


@pytest.mark.asyncio
async def test_list_services_after_unresolved_availability_force_blocks_check_availability_next():
    """Polish follow-up on #117: on a fresh session, "are you free
    tomorrow?" forced SOME tool (tool_choice="required"); the model picked
    list_services (no service was ever named, so it can't pick
    check_availability's required service itself). Stage repro showed
    iteration 2 then calling check_availability anyway, picking a service
    off that list the visitor never named — still a guess, one iteration
    later. iteration 2's tools must exclude check_availability outright so
    the model can't do that; it must ask which service instead."""
    sid = f"t-{uuid.uuid4()}"
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    calls: list = []
    responses = [
        _stream_tool_call("c1", "list_services", "{}"),
        _stream("We offer Brow Lamination, Lash Lift, and more — which service did you have in mind?"),
    ]
    service = _service_capturing_calls(responses, calls)

    async def fake_list_services(*, tool_name, tool_args=None, **kw):
        return {"branch": {"id": "b1", "name": "Main Branch"}, "services": [{"id": "s1", "name": "Brow Lamination"}]}

    with patch("app.services.clinic_agent.execute_clinic_tool", fake_list_services):
        await _run_turn(service, config, "Are you free tomorrow?", sid)

    assert len(calls) == 2
    iteration_2_tool_names = {t["function"]["name"] for t in calls[1]["tools"]}
    assert "check_availability" not in iteration_2_tool_names
    # Every other tool stays available — list_services again, search_knowledge,
    # prepare_booking, etc. — only check_availability itself is excluded.
    assert "list_services" in iteration_2_tool_names


@pytest.mark.asyncio
async def test_hours_question_does_not_force_any_tool():
    """Review on #117: "open" was dropped from _AVAILABILITY_SIGNAL —
    "what time are you open?" is an hours question (search_knowledge /
    the live-branch-hours path), not an availability one."""
    sid = f"t-{uuid.uuid4()}"
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    calls: list = []
    responses = [_stream("We're open 10am to 8pm every day.")]
    service = _service_capturing_calls(responses, calls)

    with patch("app.services.clinic_agent.execute_clinic_tool", fake_execute_clinic_tool):
        events = await _run_turn(service, config, "What time are you open?", sid)

    assert calls[0]["tool_choice"] == "auto"
    done = next(e for e in events if e["type"] == "done")
    assert done["answer"]


def test_availability_signal_no_longer_matches_bare_open():
    assert not _AVAILABILITY_SIGNAL.search("What time are you open?")


@pytest.mark.asyncio
async def test_language_switch_on_forced_availability_turn_reasserts_directive_near_generation():
    """Stage repro (follow-up on #117): a session that starts in English
    then switches to Romanized Nepali got an English reply on the
    forced-check_availability turn — B1 moved the turn's first text
    generation to AFTER a tool round, where an English tool result (plus,
    across turns, English-heavy history) is the most recent content,
    outweighing the system prompt's own per-turn LANGUAGE-THIS-TURN
    directive set once at the top of the turn. Fixed by re-asserting that
    directive as the LAST message before the next generation call."""
    from app.services.clinic_agent import _LANGUAGE_DIRECTIVES

    sid = f"t-{uuid.uuid4()}"
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    calls: list = []

    # Turn 1: English, establishes history (and the date anchor "tomorrow"
    # sets, so turn 2's forced tool_choice is the SPECIFIC check_availability
    # — matching the stage repro exactly).
    turn1_responses = [
        _stream_tool_call("c0", "check_availability", '{"service": "Brow Lamination", "date": "2026-10-07"}'),
        _stream("We have availability for Brow Lamination tomorrow at 10:00, 10:30, 11:00."),
    ]
    service = _service_capturing_calls(list(turn1_responses), calls)
    with patch("app.services.clinic_agent.execute_clinic_tool", fake_execute_clinic_tool):
        await _run_turn(service, config, "For brow lamination tomorrow", sid)

    # Turn 2: Romanized Nepali, names a specific time — forces check_availability.
    turn2_responses = [
        _stream_tool_call("c1", "check_availability", '{"service": "Brow Lamination", "date": "2026-10-07", "time": "11:30"}'),
        _stream("Brow Lamination ko 11:30 slot available cha."),
    ]
    service2 = _service_capturing_calls(list(turn2_responses), calls)
    turn2_call_start = len(calls)
    with patch("app.services.clinic_agent.execute_clinic_tool", fake_execute_clinic_tool):
        await _run_turn(service2, config, "Malai 11:30 am ko chaiyeko cha", sid)

    # The SECOND LLM call of turn 2 (iteration 2, generating the final
    # answer after the forced tool's result) must see the Romanized-Nepali
    # directive as the LAST message — not the English tool result.
    turn2_second_call = calls[turn2_call_start + 1]
    last_message = turn2_second_call["messages"][-1]
    assert last_message["role"] == "system"
    assert last_message["content"] == _LANGUAGE_DIRECTIVES["ne_romanized"].strip()
