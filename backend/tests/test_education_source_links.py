"""The chatbot points a student at the right Admizz page: one code-generated Markdown link per reply, chosen by what they asked
about and the country in context. A page link is never proof that the page is right, a selected country alone never triggers
one, a knowledge-base page comes only from a retrieved chunk's own approved url, and no card, schema or catalog number changes."""
import json

import pytest

from app.services import education_sources as src
from app.services.education_sources import Resource, SourceRegistry
from tests.test_education_agent import _catalog, _chunk, blocks_of, make_agent, run  # noqa: F401 (_catalog is autouse)

HOST = "https://admizzeducation.com"
SITE = "edu-agent-test"
MARK = "More on Admizz:"


def _r(rid, country, path, title, category, kind, **kw):
    return Resource(id=rid, country=country, url=f"{HOST}/{path}", title=title, category=category, kind=kind, **kw)


@pytest.fixture(autouse=True)
def _registry():
    src.reset_sources()
    src.register_sources(SourceRegistry(site_id=SITE, resources=[
        _r("uk-guide", "uk", "study-in-the-uk", "Study in the UK", "guide", "guide"),
        _r("uk-cost", "uk", "total-cost-uk", "Cost of Studying in the UK", "cost", "article"),
        _r("uk-fee", "uk", "answers/uk-student-visa-fee-nepal", "UK Student Visa Fee and Health Surcharge", "visa", "answer",
           published="2026-10-05", checked="2026-10", sitemap_lastmod="2026-10-08"),
        _r("uk-tb", "uk", "answers/uk-tb-test-nepal", "UK Student Visa TB Test from Nepal", "visa", "answer", checked="2026-10"),
        _r("ca-guide", "ca", "study-in-canada", "Study in Canada", "guide", "guide"),
        _r("test-prep", None, "test-prep", "Test Preparation in Nepal", "test_prep", "service"),
        _r("scholar", None, "scholarship-assistance-in-nepal", "Scholarship Assistance", "scholarship", "service"),
    ]))
    yield
    src.reset_sources()


def _answer(events):
    return events[-1]["answer"]


def _tokens(events):
    return "".join(e["data"] for e in events if e["type"] == "token")


def _links(text):
    return text.count(MARK)


# --- cards about a country ---------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_country_facts_card_gets_one_guide_link_after_its_sentence():
    agent = make_agent([[_chunk("Here are the UK facts.")]])
    events = await run(agent, "tell me about the UK", site=SITE)
    assert blocks_of(events)[0]["type"] == "info_card"
    assert _answer(events).endswith(f"{MARK} [Study in the UK]({HOST}/study-in-the-uk)")
    assert _links(_answer(events)) == 1
    assert _answer(events).split(MARK)[1] in _tokens(events)       # streamed too, not only in the final answer


@pytest.mark.asyncio
async def test_a_cost_card_gets_the_cost_page():
    agent = make_agent([[_chunk("Here is the UK cost estimate.")]])
    events = await run(agent, "how much does it cost to study in the UK", site=SITE)
    assert blocks_of(events)[0]["type"] == "cost_calculator"
    assert f"[Cost of Studying in the UK]({HOST}/total-cost-uk)" in _answer(events)


@pytest.mark.asyncio
async def test_a_visa_fee_question_gets_the_visa_answer_page_with_the_checked_date_not_the_cost_article():
    agent = make_agent([[_chunk("Here is a UK cost estimate.")]])
    events = await run(agent, "what is the uk student visa fee", site=SITE)       # the rules answer this with the cost card
    assert f"[UK Student Visa Fee and Health Surcharge]({HOST}/answers/uk-student-visa-fee-nepal) (checked October 2026)" in _answer(events)
    assert "Cost of Studying" not in _answer(events)
    assert "2026-10-05" not in _answer(events) and "5 October" not in _answer(events)   # published is not "checked"


@pytest.mark.asyncio
async def test_a_card_that_is_not_about_country_information_gets_no_link_even_with_a_country_in_context():
    agent = make_agent([[_chunk("Here is the UK.")], [_chunk("Here is what I know.")]])
    await run(agent, "tell me about the UK", site=SITE)
    events = await run(agent, "what do you know about me", site=SITE)
    assert blocks_of(events)[0]["type"] == "profile_summary"
    assert MARK not in _answer(events)


@pytest.mark.asyncio
async def test_the_same_page_is_not_offered_twice_in_a_session():
    agent = make_agent([[_chunk("Here are the UK facts.")], [_chunk("Here are the UK facts again.")]])
    first = await run(agent, "tell me about the UK", site=SITE)
    second = await run(agent, "quick facts for the UK", site=SITE)
    assert _links(_answer(first)) == 1 and MARK not in _answer(second)


@pytest.mark.asyncio
async def test_the_link_is_saved_with_the_reply_so_a_reload_shows_it():
    agent = make_agent([[_chunk("Here are the UK facts.")]])
    await run(agent, "tell me about the UK", site=SITE)
    history, _ = await agent.memory.load_history(None, "s1")
    assert any(MARK in m["content"] for m in history if m["role"] == "assistant")


@pytest.mark.asyncio
async def test_a_country_without_a_page_gets_no_link_and_no_made_up_one():
    agent = make_agent([[_chunk("Here are the Australia facts.")]])
    events = await run(agent, "tell me about Australia", site=SITE)
    assert blocks_of(events)[0]["type"] == "info_card" and MARK not in _answer(events)


@pytest.mark.asyncio
async def test_a_tenant_with_no_registry_is_unaffected():
    agent = make_agent(['{"shape": "none"}', [_chunk("I can help with that.")]])
    events = await run(agent, "tell me about the UK", site="edu-empty")        # no catalog, no registry: the normal reply
    assert MARK not in _answer(events) and _answer(events) == "I can help with that."


# --- free-text questions ------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_test_prep_question_links_the_test_prep_page_even_without_a_country():
    agent = make_agent(['{"shape": "none"}', [_chunk("We run IELTS preparation classes.")]])
    events = await run(agent, "do you offer ielts coaching classes", site=SITE)
    assert f"[Test Preparation in Nepal]({HOST}/test-prep)" in _answer(events)


@pytest.mark.asyncio
async def test_a_visa_question_with_a_country_picks_the_best_matching_answer_page():
    agent = make_agent(['{"shape": "none"}', [_chunk("A TB test may be needed.")]])
    await _seed(agent, focus_country="uk")
    events = await run(agent, "Do I need a TB test for the visa?", site=SITE)
    assert f"[UK Student Visa TB Test from Nepal]({HOST}/answers/uk-tb-test-nepal) (checked October 2026)" in _answer(events)


@pytest.mark.asyncio
async def test_a_knowledge_base_answer_links_the_page_it_was_retrieved_from():
    chunks = [{"source_title": "Study in Canada", "source_url": f"{HOST}/study-in-canada", "content": "Canada intakes are..."}]
    agent = make_agent(['{"shape": "none"}', [_chunk("Canada has several intakes.")]], chunks=chunks)
    events = await run(agent, "which intakes does canada have?", site=SITE)
    assert f"[Study in Canada]({HOST}/study-in-canada)" in _answer(events)


@pytest.mark.asyncio
async def test_a_retrieved_page_on_another_host_is_never_linked():
    chunks = [{"source_title": "Evil", "source_url": "https://evil.com/phish", "content": "Intakes are..."},
              {"source_title": "Plain", "source_url": "http://admizzeducation.com/x", "content": "Intakes are..."}]
    agent = make_agent(['{"shape": "none"}', [_chunk("There are several intakes.")]], chunks=chunks)
    events = await run(agent, "when is the next intake?", site=SITE)
    assert "evil.com" not in _answer(events) and "http://" not in _answer(events)


@pytest.mark.asyncio
async def test_a_retrieved_page_title_cannot_forge_a_link_label():
    chunks = [{"source_title": "Pay here ](https://evil.com) [now\nhttps://evil.com", "source_url": f"{HOST}/study-in-canada",
               "content": "Intakes are..."}]
    agent = make_agent(['{"shape": "none"}', [_chunk("There are several intakes.")]], chunks=chunks)
    events = await run(agent, "when is the next intake?", site=SITE)
    line = _answer(events).split(MARK)[1]
    assert "evil.com" not in line and line.count("](") == 1 and "\n" not in line.strip()


@pytest.mark.asyncio
async def test_small_talk_gets_no_link():
    agent = make_agent([[_chunk("You're welcome!")]])
    await _seed(agent, focus_country="uk")
    events = await run(agent, "thanks a lot", site=SITE)
    assert MARK not in _answer(events)


# --- when the knowledge base has no answer --------------------------------------------------------------------------------

async def _miss(country):
    agent = make_agent([json.dumps({"found": False}), [_chunk("I don't have those details; a counselor can help.")]],
                       chunks=[{"source_title": "Process FAQ", "content": "Booking a consultation..."}])
    await _seed(agent, focus_country=country)
    return await run(agent, "What is the application process?", site=SITE)


@pytest.mark.asyncio
async def test_a_knowledge_base_miss_keeps_the_counselor_reply_and_adds_the_country_guide_when_one_exists():
    events = await _miss("ca")
    assert _answer(events).startswith("I don't have")
    assert _answer(events).endswith(f"{MARK} [Study in Canada]({HOST}/study-in-canada)")
    assert [b["type"] for b in blocks_of(events)] == ["quick_chips"]    # the counselor button is still there


@pytest.mark.asyncio
async def test_a_knowledge_base_miss_without_a_guide_is_exactly_what_it_was_before():
    events = await _miss("au")                                          # no Australia page in the registry
    src.reset_sources()
    src.register_sources(SourceRegistry(site_id=SITE))
    before = await _miss("au")
    assert MARK not in _answer(events)
    assert [(e["type"], e.get("data")) for e in events if e["type"] in ("token", "ui_block")] == \
           [(e["type"], e.get("data")) for e in before if e["type"] in ("token", "ui_block")]
    assert _answer(events) == _answer(before)


# --- nothing factual moves -------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_cards_are_identical_with_and_without_a_registry():
    with_links = await run(make_agent([[_chunk("Here are the UK facts.")]]), "tell me about the UK", site=SITE)
    src.reset_sources()
    src.register_sources(SourceRegistry(site_id=SITE))
    without = await run(make_agent([[_chunk("Here are the UK facts.")]]), "tell me about the UK", site=SITE)
    assert blocks_of(with_links) == blocks_of(without)
    assert _answer(without) == "Here are the UK facts." or MARK not in _answer(without)


async def _seed(agent, **fields):
    profile = {"contact": {}, "shown": {}, **fields}
    await agent.memory.save_profile(None, "s1", profile)
