"""
SBAL-Z5 F1/F2: the "Details" button on a clinic service card synthesizes
"Tell me more about {name}" (meta_messaging.send_service_cards). That turn
already names the exact service, so it should resolve it directly via
list_services instead of wasting a search_knowledge round trip first (the
old knowledge_fast_path classified it as a plain FAQ). A single match gets
`ui.service_detail` (name/price/duration/description, no carousel); a real
multi-match still gets `ui.services` but with a `services_caption` that
follows the visitor's language instead of a hardcoded English string.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services import clinic_tools
from app.services.clinic_agent import ClinicAgentService


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000ee"),
        name="Sami's Brow and Lashes",
        site_id="sbal",
        api_key="key",
        website_type="clinic",
    )


@pytest.fixture(autouse=True)
def _reset_state():
    clinic_tools.reset_quick_facts_cache()
    clinic_tools.reset_org_cache()
    yield
    clinic_tools.reset_quick_facts_cache()
    clinic_tools.reset_org_cache()


def _chunk(content=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=None))])


async def _stream(text: str):
    yield _chunk(content=text)


def _service_for_responses(responses: list) -> ClinicAgentService:
    service = ClinicAgentService()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=lambda **kw: responses.pop(0))
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None
    return service


async def _run(service, config, question, session_id):
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
        brand_name="Sami's Brow and Lashes",
    ):
        events.append(event)
    return events


ONE_SERVICE = {
    "branch": {"id": "b1", "name": "Thamel"},
    "services": [{
        "id": "svc-1", "name": "Highly Defining Dye", "category": "Brow",
        "duration_minutes": 45, "price_npr": 1200, "description": "A bold brow tint.",
    }],
}

MANY_SERVICES = {
    "branch": {"id": "b1", "name": "Thamel"},
    "services": [
        {"id": "svc-1", "name": "Highly Defining Dye", "category": "Brow",
         "duration_minutes": 45, "price_npr": 1200, "description": "A bold brow tint."},
        {"id": "svc-2", "name": "Lash Lift", "category": "Lash",
         "duration_minutes": 60, "price_npr": 2500, "description": "Lift and set."},
    ],
}

# SBAL-Z7: "Lash Lift" is one of 5 names _list_services' loose substring
# match returns for the query "Lash Lift" (it also matches every OTHER
# name/category containing "lash" or "lift") — but exactly one of the 5
# matches the visitor's own words verbatim.
FIVE_LOOSE_ONE_EXACT = {
    "branch": {"id": "b1", "name": "Thamel"},
    "services": [
        {"id": "svc-2", "name": "Lash Lift", "category": "Lash",
         "duration_minutes": 60, "price_npr": 2500, "description": "Lift and set."},
        {"id": "svc-3", "name": "Lash Lift Removal", "category": "Lash",
         "duration_minutes": 20, "price_npr": 800, "description": "Removes a prior lift."},
        {"id": "svc-4", "name": "Classic Lash Extension", "category": "Lash",
         "duration_minutes": 90, "price_npr": 3500, "description": "Classic extensions."},
        {"id": "svc-5", "name": "Volume Lash Lift", "category": "Lash",
         "duration_minutes": 75, "price_npr": 3000, "description": "Volume lift."},
        {"id": "svc-6", "name": "Brow Lift", "category": "Brow",
         "duration_minutes": 40, "price_npr": 1800, "description": "Brow lift treatment."},
    ],
}


@pytest.mark.asyncio
async def test_details_postback_resolves_via_list_services_not_search_knowledge():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    service = _service_for_responses([
        _stream("Highly Defining Dye is NPR 1200 and takes 45 minutes — a bold brow tint."),
    ])

    with patch(
        "app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=ONE_SERVICE),
    ) as mock_tool:
        events = await _run(
            service, config, "Tell me more about Highly Defining Dye", session_id="details-1",
        )

    # One LLM call (fast-pathed, like the knowledge collapse), and the ONLY
    # execute_clinic_tool call this turn is list_services — never
    # search_knowledge.
    assert service.client.chat.completions.create.await_count == 1
    assert mock_tool.await_count == 1
    assert mock_tool.await_args.kwargs["tool_name"] == "list_services"
    assert mock_tool.await_args.kwargs["tool_args"] == {"query": "Highly Defining Dye"}

    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["ui"]["service_detail"]["name"] == "Highly Defining Dye"
    assert done_event["ui"]["service_detail"]["price"] == 1200
    assert done_event["ui"]["service_detail"]["duration"] == 45
    assert "services" not in done_event["ui"]


@pytest.mark.asyncio
async def test_details_postback_prompt_carries_result_and_drops_both_tools():
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    captured_calls: list = []

    def _create(**kw):
        captured_calls.append(kw)
        return _stream("Highly Defining Dye is NPR 1200 and takes 45 minutes.")

    service = ClinicAgentService()
    service.client = AsyncMock()
    service.client.chat.completions.create = AsyncMock(side_effect=_create)
    service.conversation_store = AsyncMock()
    service.conversation_store.get_messages = lambda session_id: []
    service.conversation_store.add_message = lambda *a, **kw: None

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=ONE_SERVICE)):
        await _run(service, config, "Tell me more about Highly Defining Dye", session_id="details-2")

    system_prompt = captured_calls[0]["messages"][0]["content"]
    assert "SERVICE-THIS-TURN" in system_prompt
    assert "Highly Defining Dye" in system_prompt
    tool_names = {t["function"]["name"] for t in captured_calls[0]["tools"]}
    assert "list_services" not in tool_names
    assert "search_knowledge" not in tool_names
    assert {"check_availability", "prepare_booking", "confirm_booking"} <= tool_names


@pytest.mark.asyncio
async def test_details_postback_with_multiple_matches_gets_carousel_and_caption():
    """A "Details" tap whose name matches more than one service (loose
    substring match) falls back to the carousel — with a caption, not the
    old hardcoded English string."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    service = _service_for_responses([_stream("Here are a couple of matching services.")])

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=MANY_SERVICES)):
        events = await _run(service, config, "Tell me more about Lash", session_id="details-3")

    done_event = next(e for e in events if e["type"] == "done")
    assert len(done_event["ui"]["services"]) == 2
    assert done_event["ui"]["services_caption"] == "Here are our services — swipe to see them."
    assert "service_detail" not in done_event["ui"]


@pytest.mark.asyncio
async def test_details_postback_exact_name_match_wins_over_loose_matches():
    """SBAL-Z7: "Tell me more about Lash Lift" named the service EXACTLY —
    even though list_services' loose substring match also pulls in 4 other
    "lash"/"lift" services, the one exact (case-insensitive, trimmed) name
    match wins outright and gets service_detail, not a 5-card carousel."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    service = _service_for_responses([_stream("Lash Lift is NPR 2500 and takes 60 minutes.")])

    with patch(
        "app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=FIVE_LOOSE_ONE_EXACT),
    ):
        events = await _run(service, config, "Tell me more about Lash Lift", session_id="details-exact-1")

    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["ui"]["service_detail"]["id"] == "svc-2"
    assert done_event["ui"]["service_detail"]["name"] == "Lash Lift"
    assert "services" not in done_event["ui"]


@pytest.mark.asyncio
async def test_details_postback_loose_query_with_no_exact_match_stays_multi():
    """"lash" (lowercase, no exact name match among the 5 loose hits)
    keeps today's carousel behaviour — the exact-match shortcut only fires
    when one of the candidates matches verbatim."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    service = _service_for_responses([_stream("Here are our lash-related services.")])

    with patch(
        "app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=FIVE_LOOSE_ONE_EXACT),
    ):
        events = await _run(service, config, "Tell me more about lash", session_id="details-exact-2")

    done_event = next(e for e in events if e["type"] == "done")
    assert len(done_event["ui"]["services"]) == 5
    assert "service_detail" not in done_event["ui"]


@pytest.mark.asyncio
async def test_multi_match_caption_localizes_for_romanized_nepali():
    """F2: the Details postback's synthesized text ("Tell me more about
    X") is always in English — it's our own button's wording, not the
    visitor's — so its fast path's caption can only ever reflect that.
    Real localization is exercised by the visitor's own free-text query
    through the main tool loop, which is what this covers: a Romanized
    Nepali multi-match question gets the Romanized caption, not English."""
    from types import SimpleNamespace as _SN

    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)

    def _tool_call_chunk(call_id, name, arguments):
        return _SN(choices=[_SN(delta=_SN(
            content=None,
            tool_calls=[_SN(index=0, id=call_id, function=_SN(name=name, arguments=arguments))],
        ))])

    async def _stream_tool_call(call_id, name, arguments):
        yield _tool_call_chunk(call_id, name, arguments)

    service = _service_for_responses([
        _stream_tool_call("call_1", "list_services", '{"query": "lash"}'),
        _stream("Yeeh haru matching services ho."),
    ])

    with patch("app.services.clinic_agent.execute_clinic_tool", AsyncMock(return_value=MANY_SERVICES)):
        events = await _run(
            service, config, "Lash ko barema tapai ke bhannu huncha?", session_id="details-4",
        )

    done_event = next(e for e in events if e["type"] == "done")
    assert done_event["ui"]["services_caption"] == "Hamro services haru yaha chan — swipe garera hernuhos."


@pytest.mark.asyncio
async def test_plain_services_question_still_uses_knowledge_fast_path():
    """Regression: a normal FAQ question (not the Details postback's exact
    "Tell me more about X" text) is unaffected — still search_knowledge."""
    config = WidgetConfig(customer_id=uuid.uuid4(), brand_name="SBAL", contact_phone=None)
    service = _service_for_responses([_stream("We're open 10 AM to 8 PM every day.")])

    with patch(
        "app.services.clinic_agent.execute_clinic_tool",
        AsyncMock(return_value={"chunks": [{"content": "Hours: 10 AM - 8 PM daily."}]}),
    ) as mock_tool:
        await _run(service, config, "What are your opening hours?", session_id="faq-unaffected")

    assert mock_tool.await_args.kwargs["tool_name"] == "search_knowledge"
