"""SBAL-Z12: voice time-to-first-token. F1 — transliterated "services" must not
be classified knowledge-only (4.1 s wasted prefetch). F2 — list_services tool
result handed to the model is capped on voice only."""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.widget_config import WidgetConfig
from app.services import clinic_tools
from datetime import datetime
from app.services.clinic_agent import (
    NPT,
    ClinicAgentService,
    _VOICE_SERVICES_CAP,
    _cap_services_for_voice,
    _is_knowledge_only_turn,
)
from tests.test_clinic_faq_collapse import (
    _make_customer, _service_for_responses, _stream, _stream_tool_call, _reset_state,  # noqa: F401
)


@pytest.mark.parametrize("q", [
    "कुन कुन सर्भिसेसहरू छ?",   # the call that died
    "सर्भिसेस के के छ?",
    "तपाईको सर्विसहरू के के छन्?",
    "तपाईको सेवा के के छ?",       # the form that already worked
])
def test_devanagari_service_forms_are_not_knowledge_only(q):
    assert _is_knowledge_only_turn(q, datetime.now(NPT)) is False


def test_real_faq_still_knowledge_only():
    assert _is_knowledge_only_turn("What are your opening hours?", datetime.now(NPT)) is True


def _catalog(n):
    return {"branch": {"id": "b", "name": "B"},
            "services": [{"id": str(i), "name": f"S{i}", "price_npr": 100} for i in range(n)]}


def test_cap_truncates_and_says_so():
    r = _cap_services_for_voice(_catalog(53))
    assert len(r["services"]) == _VOICE_SERVICES_CAP
    assert r["truncated"] is True and r["total_services"] == 53
    assert "more" in r["note"]


def test_cap_leaves_small_and_blocked_results_untouched():
    small = _catalog(_VOICE_SERVICES_CAP)
    assert _cap_services_for_voice(small) is small
    blocked = {"blocked": True, "services": _catalog(53)["services"]}
    assert _cap_services_for_voice(blocked) is blocked


async def _run_channel(channel, catalog):
    seen = []
    responses = [_stream_tool_call("c1", "list_services", "{}"), _stream("ok")]
    service = _service_for_responses(responses)
    inner = service.client.chat.completions.create.side_effect

    def spy(**kw):
        seen.append(json.loads(json.dumps(kw["messages"], default=str)))
        return inner(**kw)
    service.client.chat.completions.create.side_effect = spy
    customer = _make_customer()
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="Dental City", contact_phone=None)
    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=json.loads(json.dumps(catalog)))):
        async for _ in service.process_agent_stream(
            db=AsyncMock(), site_id="dental-city", session_id=f"z12-{uuid.uuid4()}",
            question="Which services do you have?", customer_id=customer.id,
            customer=customer, config=config, brand_name="Dental City", channel=channel,
        ):
            pass
    tool_msgs = [m for m in seen[-1] if isinstance(m, dict) and m.get("role") == "tool"]
    return tool_msgs[-1]["content"]


@pytest.mark.asyncio
async def test_voice_model_sees_capped_list():
    content = json.loads(await _run_channel("voice", _catalog(53)))
    assert len(content["services"]) == _VOICE_SERVICES_CAP and content["truncated"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["chat", "instagram"])
async def test_non_voice_tool_result_byte_identical(channel):
    cat = _catalog(53)
    content = await _run_channel(channel, cat)
    assert content == json.dumps(cat)
