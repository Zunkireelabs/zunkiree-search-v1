"""EdgeX website chat calls the education agent from its server: (1) a shared server key moves the rate limit from the
visitor address to the chat session, (2) channel "text" writes cards into the answer as plain text, (3) the `done` event
says whether a person should take over. No key, no change: the browser path behaves exactly as before."""
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.query import QueryRequest, submit_query_stream
from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.education_handoff import asks_for_person, blocks_as_text, needs_human_reason
from app.utils.rate_limit import CHAT_LIMIT, reset_rate_limits
from tests.test_education_agent import PROCESS_CHUNKS, _chunk, _catalog, blocks_of, make_agent, run  # noqa: F401 (fixture)

SITE = "edu-edgex-test"
KEY = "s3cret-shared-key"


@pytest.fixture(autouse=True)
def _fresh():
    reset_rate_limits()
    yield
    reset_rate_limits()


# --- asking for a person ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "can I talk to a counsellor?", "I want to speak to a real person", "please call me", "connect me with someone",
    "need a human agent", "Can I talk with your team", "get in touch with a counselor",
])
def test_asking_for_a_person_is_recognised(text):
    assert asks_for_person(text)


@pytest.mark.parametrize("text", [
    "Study in the UK", "how much is counselling", "what does a counselor fee cover", "tell me about the team at Admizz",
    "which universities have a call for applications", "",
])
def test_ordinary_questions_are_not_a_request_for_a_person(text):
    assert not asks_for_person(text)


def test_reason_prefers_the_visitors_request_then_a_missing_answer_then_none():
    assert needs_human_reason(question="talk to a counsellor", kb_miss=True, grounding_empty=False) == "asked_for_person"
    assert needs_human_reason(question="visa steps", kb_miss=True, grounding_empty=False) == "out_of_knowledge"
    assert needs_human_reason(question="visa steps", kb_miss=False, grounding_empty=True) == "out_of_knowledge"
    assert needs_human_reason(question="Study in the UK", kb_miss=False, grounding_empty=False) is None


def test_blocks_become_text_lines_without_the_button_only_chips():
    blocks = [SimpleNamespace(type="course_list", fallback_text="3 matching courses: MSc A; MSc B"),
              SimpleNamespace(type="quick_chips", fallback_text="Next: Talk to a counselor"),
              SimpleNamespace(type="cost_table", fallback_text="  ")]
    assert blocks_as_text(blocks) == "3 matching courses: MSc A; MSc B"


# --- the agent on the text channel -----------------------------------------------------------------------------------

async def _run_text(agent, question, site="edu-agent-test"):
    events = []
    db = SimpleNamespace(commit=AsyncMock())
    async for e in agent.process_agent_stream(db=db, site_id=site, session_id="s1", question=question, customer_id=None,
                                              customer=None, config=None, brand_name="Admizz", channel="text"):
        events.append(e)
    return events


@pytest.mark.asyncio
async def test_text_channel_writes_the_card_into_the_answer_and_needs_no_human():
    agent = make_agent([[_chunk("Here you go!")]])
    events = await _run_text(agent, "I want to study abroad")
    done = events[-1]
    assert done["needs_human"] is False and done["needs_human_reason"] is None
    widget = (await run(make_agent([[_chunk("Here you go!")]]), "I want to study abroad"))[-1]["answer"]
    assert done["answer"].startswith(widget)                # the same lead-in the widget gets...
    assert "Which countries are you interested in?" in done["answer"]   # ...plus the card's fallback text


@pytest.mark.asyncio
async def test_text_channel_flags_a_question_the_knowledge_base_cannot_answer():
    agent = make_agent([json.dumps({"found": False}), [_chunk("I don't have those details; a counselor can help.")]],
                       chunks=PROCESS_CHUNKS)
    done = (await _run_text(agent, "What is the application process?"))[-1]
    assert done["needs_human"] is True and done["needs_human_reason"] == "out_of_knowledge"


@pytest.mark.asyncio
async def test_text_channel_flags_a_visitor_who_asks_for_a_person():
    agent = make_agent([[_chunk("Sure.")], [_chunk("Sure.")]])
    done = (await _run_text(agent, "can I talk to a counsellor?"))[-1]
    assert done["needs_human"] is True and done["needs_human_reason"] == "asked_for_person"


@pytest.mark.asyncio
async def test_the_widget_channel_is_unchanged():
    agent = make_agent([[_chunk("Here you go!")]])
    done = (await run(agent, "I want to study abroad"))[-1]
    assert "needs_human" not in done and "needs_human_reason" not in done
    assert "Which countries are you interested in?" not in done["answer"]   # the card is not written into a widget answer


# --- the endpoint: server key ----------------------------------------------------------------------------------------

def _customer():
    return Customer(id=uuid.UUID("00000000-0000-0000-0000-0000000000ee"), name="Edu", site_id=SITE, api_key="k",
                    website_type="education")


def _agent():
    agent = MagicMock()
    agent.calls = 0

    async def gen(**kw):
        agent.calls += 1
        yield {"type": "done", "answer": "ok", "suggestions": [], "sources": []}
    agent.process_agent_stream = gen
    return agent


async def _send(agent, *, key=None, server_key=KEY, ip="203.0.113.9", session="s1"):
    customer = _customer()
    headers = {"x-forwarded-for": ip}
    if key is not None:
        headers["x-edgex-key"] = key
    request = AsyncMock()
    request.headers, request.client = headers, SimpleNamespace(host="10.0.0.2")
    with patch("app.api.query.get_query_service") as qs, \
         patch("app.api.query.require_allowed_origin", AsyncMock()), \
         patch("app.api.query.settings.edgex_server_key", server_key), \
         patch("app.services.education_agent.get_education_agent_service", return_value=agent):
        qs.return_value._get_customer = AsyncMock(return_value=customer)
        qs.return_value._get_widget_config = AsyncMock(return_value=WidgetConfig(customer_id=customer.id, brand_name="Edu"))
        response = await submit_query_stream(
            request, QueryRequest(site_id=SITE, question="hello", session_id=session, channel="text"), db=AsyncMock())
        "".join([c async for c in response.body_iterator])


@pytest.mark.asyncio
async def test_a_wrong_key_is_refused_with_401_before_the_ai_runs():
    agent = _agent()
    with pytest.raises(HTTPException) as e:
        await _send(agent, key="nope")
    assert e.value.status_code == 401 and e.value.detail["code"] == "INVALID_SERVER_KEY"
    assert agent.calls == 0


@pytest.mark.asyncio
async def test_with_the_key_different_chats_from_one_address_do_not_block_each_other():
    agent = _agent()
    for i in range(CHAT_LIMIT + 5):
        await _send(agent, key=KEY, session=f"chat-{i}")     # one EdgeX server address, many chats
    assert agent.calls == CHAT_LIMIT + 5


@pytest.mark.asyncio
async def test_with_the_key_one_chat_is_still_limited():
    agent = _agent()
    for _ in range(CHAT_LIMIT):
        await _send(agent, key=KEY, session="same")
    with pytest.raises(HTTPException) as e:
        await _send(agent, key=KEY, session="same")
    assert e.value.status_code == 429


@pytest.mark.asyncio
async def test_with_the_key_a_missing_session_id_is_still_refused():
    agent = _agent()
    with pytest.raises(HTTPException) as e:
        await _send(agent, key=KEY, session="")
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_no_key_header_keeps_the_per_address_limit():
    agent = _agent()
    for i in range(CHAT_LIMIT):
        await _send(agent, session=f"s{i}")
    with pytest.raises(HTTPException) as e:
        await _send(agent, session="fresh")
    assert e.value.status_code == 429


@pytest.mark.asyncio
async def test_server_key_not_configured_ignores_the_header():
    agent = _agent()
    for i in range(CHAT_LIMIT):
        await _send(agent, key="anything", server_key="", session=f"s{i}")
    with pytest.raises(HTTPException) as e:
        await _send(agent, key="anything", server_key="", session="fresh")
    assert e.value.status_code == 429            # still counted per address, as if no header was sent
