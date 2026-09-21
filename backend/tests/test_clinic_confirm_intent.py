"""CLINIC-CONFIRM-INTENT-BRIEF: a clear yes to a pending read-back must reach
confirm_booking deterministically, not depend on the model picking the tool."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.widget_config import WidgetConfig
from app.services import clinic_tools
from app.services.clinic_agent import is_clear_confirmation
from tests.test_clinic_booking_truth import _run, _service_for_responses, _stream, _stream_tool_call

_PENDING = {
    "service_id": "svc1", "service_name": "General Dentistry", "branch_id": "b1",
    "branch_name": "Main", "date": "2026-09-22", "time": "10:00", "full_name": "TEST X",
    "phone_e164": "+9779800000034", "prepared_turn": 1,
}


@pytest.mark.parametrize("msg", [
    "Yes, please book it.", "yes", "Okay, go ahead!", "हुन्छ, गर्दिनुस्।", "हुन्छ",
    "ठीक छ", "huncha, garidinus", "Yes please",
])
def test_clear_confirmations(msg):
    assert is_clear_confirmation(msg)


@pytest.mark.parametrize("msg", [
    "", "no", "yes but make it 11:00", "yes, change my phone to 9841234567", "what is the price?",
    "yes, and also cleaning", "हुँदैन", "please wait", "yes tomorrow",
])
def test_not_confirmations(msg):
    assert not is_clear_confirmation(msg)


def _seed(session_id, prepared_turn=1):
    clinic_tools.reset_session_state(session_id)
    clinic_tools._state(session_id)["pending"] = {**_PENDING, "prepared_turn": prepared_turn}
    clinic_tools.mark_readback(session_id, 1)


@pytest.mark.asyncio
async def test_yes_forces_confirm_even_if_model_would_reprepare():
    """The failing EN-3 shape: the model's next output would be prepare_booking.
    Code must call confirm_booking first; the model only narrates."""
    sid = f"t-{uuid.uuid4()}"
    _seed(sid)
    from app.services import clinic_agent
    clinic_agent._TURN_COUNTERS[sid] = 1
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    service = _service_for_responses([_stream("Booked. The clinic will confirm.")])
    ex = AsyncMock(return_value={"booking": {"booking_number": "BK-1"}})
    with patch("app.services.clinic_agent.execute_clinic_tool", ex):
        events = await _run(service, config, "Yes, please book it.", session_id=sid)
    assert ex.await_args.kwargs["tool_name"] == "confirm_booking"
    assert next(e for e in events if e["type"] == "done")["answer"]


@pytest.mark.asyncio
async def test_no_forced_confirm_without_pending_or_same_turn():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    sid = f"t-{uuid.uuid4()}"
    clinic_tools.reset_session_state(sid)
    service = _service_for_responses([_stream("What service?")])
    ex = AsyncMock()
    with patch("app.services.clinic_agent.execute_clinic_tool", ex):
        await _run(service, config, "yes", session_id=sid)
    ex.assert_not_awaited()
    # prepared this same turn -> not awaiting confirmation
    _seed(sid, prepared_turn=1)
    assert clinic_tools.get_awaiting_confirmation(sid, 1) is None
    assert clinic_tools.get_awaiting_confirmation(sid, 2) is not None


@pytest.mark.asyncio
async def test_okay_after_unrelated_turn_does_not_force_confirm():
    """Read-back at turn 1, unrelated turn 2, "okay" at turn 3: no booking."""
    sid = f"t-{uuid.uuid4()}"
    _seed(sid)
    assert clinic_tools.get_awaiting_confirmation(sid, 2) is not None
    assert clinic_tools.get_awaiting_confirmation(sid, 3) is None
    from app.services import clinic_agent
    clinic_agent._TURN_COUNTERS[sid] = 2
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    service = _service_for_responses([_stream("Sure, anything else?")])
    ex = AsyncMock()
    with patch("app.services.clinic_agent.execute_clinic_tool", ex):
        await _run(service, config, "okay", session_id=sid)
    ex.assert_not_awaited()


# --- NE-4: substitution stated in the read-back ---
from app.services.clinic_agent import _build_booking_readback

_RB = {
    "service_name": "General Dentistry", "date": "2026-09-22", "time": "10:00",
    "full_name": "TEST X", "phone_e164": "+9779800000034", "branch_name": "Main", "price_npr": 2000,
}


@pytest.mark.parametrize("lang,fragment", [
    ("en", "We don't offer teeth cleaning, but General Dentistry is available."),
    ("ne_devanagari", "teeth cleaning सेवा उपलब्ध छैन, तर General Dentistry उपलब्ध छ।"),
    ("ne_romanized", "teeth cleaning sewa uplabdha chaina, tara General Dentistry uplabdha cha."),
])
def test_substitution_prefix_then_full_readback(lang, fragment):
    out = _build_booking_readback({**_RB, "substituted_for": "teeth cleaning"}, lang)
    assert out.startswith(fragment)
    assert "9800000034" in out and "TEST X" in out and "10:00" in out


@pytest.mark.parametrize("lang", ["en", "ne_devanagari", "ne_romanized"])
def test_no_prefix_when_service_matches(lang):
    base = _build_booking_readback(_RB, lang)
    assert _build_booking_readback({**_RB, "substituted_for": None}, lang) == base
    assert _build_booking_readback({**_RB, "substituted_for": "general dentistry"}, lang) == base


# --- CLINIC-CONFIRM-EXPLICIT-YES-BRIEF: gate corpus ---
import asyncio  # noqa: E402

import pytest as _pytest  # noqa: E402

from app.services import clinic_tools as _ct  # noqa: E402

_YES = [
    "yes", "Yes, please book it.", "yeah", "sure", "book it", "confirm", "ok", "okay",
    "हो", "हुन्छ", "हस्", "हजुर", "हाँ", "हाँ, हुन्छ, बुक गर्दिनु", "गर्नुहोस्", "गर्दिनुस्",
    "ठीक छ", "huncha", "ho", "has", "hajur", "garidinus", "thik cha",
]
_REASK = [
    "हुँ।", "हुँ", "hmm", "uh", "अँ", "ok?", "okay?", "हो?", "yes?", "",
    "no", "not yet", "wait", "होइन", "नगर्नुस्", "गर्दिनँ", "hoina", "yes but change the time",
    "what time is it?", "can you book it?", "book it for friday", "गर्दिन",
]


@_pytest.mark.parametrize("msg", _YES)
def test_gate_allow_list_passes(msg):
    assert is_clear_confirmation(msg), msg


@_pytest.mark.parametrize("msg", _REASK)
def test_gate_fillers_negations_questions_reask(msg):
    assert not is_clear_confirmation(msg), msg


def test_one_letter_trap_gardinu_vs_gardinam():
    assert is_clear_confirmation("बुक गर्दिनु")
    assert not is_clear_confirmation("बुक गर्दिनँ")


def _stage_pending(sid):
    _ct.reset_session_state(sid)
    st = _ct._state(sid)
    st["pending"] = {
        "service_id": "svc", "date": "2026-09-25", "time": "10:00", "prepared_turn": 1,
        "branch_id": "b", "full_name": "Probe Test", "phone_e164": "+9779812345678",
    }
    return st


@_pytest.mark.asyncio
async def test_confirm_reasks_on_filler_and_never_writes(monkeypatch):
    _stage_pending("gate1")
    writes = []

    async def fake_exec(*a, **k):
        writes.append(1)
        return {"booking_number": "BK-1"}

    monkeypatch.setattr(_ct, "_execute_booking", fake_exec)
    for msg in ("हुँ।", "hmm", None):
        r = await _ct._confirm_booking(None, None, "gate1", 2, msg)
        assert r["error"] == "NEEDS_EXPLICIT_YES"
    assert writes == []


@_pytest.mark.asyncio
async def test_concurrent_double_confirm_writes_at_most_once(monkeypatch):
    _stage_pending("gate2")
    writes = []

    async def slow_exec(*a, **k):
        writes.append(1)
        await asyncio.sleep(0.05)  # both confirms are in flight during the write
        return {"booking_number": "BK-1"}

    monkeypatch.setattr(_ct, "_execute_booking", slow_exec)
    a, b = await asyncio.gather(
        _ct._confirm_booking(None, None, "gate2", 2, "yes"),
        _ct._confirm_booking(None, None, "gate2", 2, "हुन्छ"),
    )
    assert len(writes) == 1
    assert sorted(bool(r.get("already_booked")) for r in (a, b)) == [False, True]


@_pytest.mark.asyncio
async def test_write_survives_caller_cancellation_and_is_recorded(monkeypatch):
    st = _stage_pending("gate3")
    writes = []

    async def slow_exec(*a, **k):
        writes.append(1)
        await asyncio.sleep(0.1)
        return {"booking_number": "BK-1"}

    monkeypatch.setattr(_ct, "_execute_booking", slow_exec)
    t = asyncio.ensure_future(_ct._confirm_booking(None, None, "gate3", 2, "yes"))
    await asyncio.sleep(0.02)
    t.cancel()
    with _pytest.raises(asyncio.CancelledError):
        await t
    await asyncio.sleep(0.2)  # the shielded write finishes on its own
    assert len(st["confirmed"]) == 1
    retry = await _ct._confirm_booking(None, None, "gate3", 3, "yes")
    assert retry["already_booked"] is True and writes == [1]


@_pytest.mark.asyncio
async def test_gate_logs_result_without_user_text(monkeypatch, caplog):
    import logging
    _stage_pending("gate4")

    async def fake_exec(*a, **k):
        return {"booking_number": "BK-1"}

    monkeypatch.setattr(_ct, "_execute_booking", fake_exec)
    with caplog.at_level(logging.INFO):
        await _ct._confirm_booking(None, None, "gate4", 2, "हुँ।")
        await _ct._confirm_booking(None, None, "gate4", 2, "yes")
    lines = [r.getMessage() for r in caplog.records if "confirm_gate" in r.getMessage()]
    assert lines == ["[CLINIC-AGENT] confirm_gate result=reask", "[CLINIC-AGENT] confirm_gate result=pass"]
