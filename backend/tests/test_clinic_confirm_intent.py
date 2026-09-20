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
