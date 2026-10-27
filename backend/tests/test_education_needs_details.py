"""'Which country is best for me?' before the bot knows anything it can rank on. Seen live: a student wrote "i have 3 gpa which
country could be the best" and got a budget slider with an LLM sentence that ignored the question. Now code shows the slider
and says why: "To suggest countries I need a few details about you. Let's start with your yearly budget." """
import re

import pytest

from app.services import education_agent
from app.services.education_agent import _ask_for_budget
from app.services.education_catalog import Catalog, CountryRecord, register_catalog
from app.services.education_leadins import NEEDS_DETAILS
from app.services.education_profile import apply_updates, new_profile
from tests.test_education_agent import _chunk, _tool_chunk, blocks_of, make_agent, run
from tests.test_education_consistency import make_catalog

# The first live message carried a GPA. Scores in a question are now saved (see the end of this file), so it no longer needs a budget;
# this is the same shape of question with nothing to rank on.
SCREENSHOT_MESSAGE = "which country could be the best for me"
OLD_SCREENSHOT_MESSAGE = "i have 3 gpa which country could be the best"


@pytest.fixture(autouse=True)
def _agent_catalog():
    from app.services import education_kb_blocks
    education_kb_blocks._llm_shape_cache.clear()
    education_kb_blocks._shared_cache.clear()
    cat = make_catalog()
    cat.site_id = "edu-agent-test"
    register_catalog(cat)
    # a tenant whose catalog has no costs or requirements at all: nothing to rank, nothing to slide over
    register_catalog(Catalog(site_id="edu-bare", countries=[CountryRecord(id="uk", label="U.K.", aliases=["UK"])]))


def seed(agent, **fields):
    p = new_profile()
    apply_updates(p, fields)
    agent.memory.profiles[(None, "s1")] = p


def text_of(events):
    return "".join(e["data"] for e in events if e["type"] == "token")


def kinds(events):
    return [b["type"] for b in blocks_of(events)]


# ---- the fix ----

@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["Which countries fit my profile?", SCREENSHOT_MESSAGE, "which country is best for me"])
async def test_with_nothing_to_rank_on_the_bot_asks_for_the_budget_and_says_why(message):
    agent = make_agent([])                              # an empty script: any LLM call would fail the test
    events = await run(agent, message)
    assert kinds(events) == ["range_slider"]
    assert text_of(events) == NEEDS_DETAILS and agent.client.calls == []
    [slider] = blocks_of(events)
    assert slider["data"]["field"] == "budget" and not slider.get("answered")
    assert events[-1]["type"] == "done" and events[-1]["answer"] == NEEDS_DETAILS


@pytest.mark.asyncio
async def test_the_sentence_is_saved_with_the_message():
    agent = make_agent([])
    await run(agent, SCREENSHOT_MESSAGE)
    [_, assistant] = await agent.memory.list_messages(None, "s1")
    assert assistant["content"] == NEEDS_DETAILS and [b["type"] for b in assistant["blocks"]] == ["range_slider"]


def test_the_sentence_explains_and_asks_without_naming_a_country_or_a_number():
    assert "budget" in NEEDS_DETAILS and "few details" in NEEDS_DETAILS
    assert not re.search(r"\d|\b(best|guarantee|universit\w+|program)\b", NEEDS_DETAILS, re.I)
    assert not any(label in NEEDS_DETAILS for label in ("U.K.", "Australia", "Canada", "Germany"))


@pytest.mark.asyncio
async def test_the_slider_then_a_second_ask_gives_the_real_recommendation():
    agent = make_agent([[_chunk("Here you go.")]])
    first = await run(agent, SCREENSHOT_MESSAGE)
    slider = blocks_of(first)[0]
    tap = {"blockId": slider["block_id"], "blockType": "range_slider", "actionId": "set_value",
           "values": {"field": "budget", "value": 40000}, "displayText": "My budget is $40,000 per year"}
    await run(agent, "My budget is $40,000 per year", block_action=tap)         # a real tap, so tap validation passes too
    again = await run(agent, "Which countries fit my profile?")
    assert kinds(again) == ["profile_summary", "match_cards", "quick_chips"]


# ---- when it must NOT ask ----

@pytest.mark.asyncio
@pytest.mark.parametrize("fields", [dict(english_score=6.5), dict(academic_score=70)])
async def test_one_known_requirement_is_enough_to_rank_so_no_budget_is_asked(fields):
    agent = make_agent([])
    seed(agent, **fields)
    assert kinds(await run(agent, "Which countries fit my profile?")) == ["profile_summary", "match_cards", "quick_chips"]


@pytest.mark.asyncio
async def test_a_known_budget_is_never_asked_again_even_if_nothing_can_be_ranked():
    agent = make_agent([[_chunk("I can't rank yet; a counselor can help.")]])
    seed(agent, budget=30000)
    events = await run(agent, "Which countries fit my profile?", site="edu-bare")
    assert "range_slider" not in kinds(events)
    assert "tools" in agent.client.calls[0] and text_of(events) == "I can't rank yet; a counselor can help."   # the old path


@pytest.mark.asyncio
async def test_without_cost_data_there_is_no_slider_so_the_llm_path_remains():
    agent = make_agent([[_chunk("What is your budget?")]])
    events = await run(agent, "Which countries fit my profile?", site="edu-bare")
    assert kinds(events) == [] and "tools" in agent.client.calls[0]


@pytest.mark.asyncio
async def test_the_remembered_card_on_screen_is_not_replaced_by_the_ask():
    agent = make_agent([])
    seed(agent)
    agent.memory.profiles[(None, "s1")]["ui_state"] = {"intent": "compare", "args": {"countries": ["uk", "au"]},
                                                      "ui": {"type": "comparison_table", "version": 2}}
    await run(agent, SCREENSHOT_MESSAGE)
    assert agent.memory.profiles[(None, "s1")]["ui_state"]["intent"] == "compare"


# ---- other languages, the LLM path, and the switch ----

@pytest.mark.asyncio
async def test_a_message_in_another_language_still_gets_the_slider_with_an_llm_sentence():
    agent = make_agent([[_chunk("Pahile tapaiko barshik budget set garnus.")]])
    events = await run(agent, "malai kun country ramro cha, Which countries fit my profile?")
    assert kinds(events) == ["range_slider"] and text_of(events) == "Pahile tapaiko barshik budget set garnus."
    assert "tools" not in agent.client.calls[0]
    note = " ".join(m["content"] for m in agent.client.calls[0]["messages"] if m["role"] == "system")
    assert "countries can't be ranked until you know their budget" in note


@pytest.mark.asyncio
async def test_when_the_llm_picks_the_matches_tool_with_nothing_to_rank_on_it_gets_the_same_answer():
    agent = make_agent([[_tool_chunk("show_country_matches", {})]])
    events = await run(agent, "Suggest some places where I could do my masters")
    assert kinds(events) == ["range_slider"] and text_of(events) == NEEDS_DETAILS
    assert len(agent.client.calls) == 1
    assert agent.memory.profiles[(None, "s1")].get("ui_state") is None


@pytest.mark.asyncio
async def test_with_the_switch_off_the_old_behaviour_returns(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_template_leadins", False)
    agent = make_agent([[_chunk("What is your budget?")]])
    events = await run(agent, SCREENSHOT_MESSAGE)
    assert kinds(events) == [] and "tools" in agent.client.calls[0]


# ---- the helper ----

def test_ask_for_budget_returns_the_slider_only_when_it_helps():
    cat = make_catalog()
    empty = new_profile()
    assert _ask_for_budget(empty, cat).block.type == "range_slider"
    known = new_profile()
    apply_updates(known, {"budget": 30000})
    assert _ask_for_budget(known, cat) is None
    assert _ask_for_budget(empty, Catalog(site_id="edu-bare", countries=[CountryRecord(id="uk", label="U.K.")])) is None


# ---- seen live (2026-10-14): the question carried the scores, then the bot asked the budget, then asked "which countries?" ----

LIVE_MESSAGE = "which is the best country for me i have 7 ielts score and 3.64 gpa"


@pytest.mark.asyncio
async def test_scores_in_the_question_are_saved_and_the_bot_ranks_straight_away_without_asking_the_budget():
    agent = make_agent([])
    events = await run(agent, LIVE_MESSAGE)
    assert kinds(events) == ["profile_summary", "match_cards", "quick_chips"] and "range_slider" not in kinds(events)
    profile = agent.memory.profiles[(None, "s1")]
    assert profile["english_score"] == 7 and profile["academic_gpa"] == 3.64


@pytest.mark.asyncio
async def test_after_the_budget_the_bot_finishes_the_recommendation_instead_of_asking_which_countries():
    agent = make_agent([])
    first = await run(agent, "which country is best for me")                       # nothing to rank on: the slider
    slider = blocks_of(first)[0]
    tap = {"blockId": slider["block_id"], "blockType": "range_slider", "actionId": "set_value",
           "values": {"field": "budget", "value": 40000}, "displayText": "My budget is $40,000 per year"}
    second = await run(agent, "My budget is $40,000 per year", block_action=tap)
    assert kinds(second) == ["profile_summary", "match_cards", "quick_chips"]       # NOT a "which countries?" card
    assert "choice" not in kinds(second)


@pytest.mark.asyncio
async def test_a_pending_recommendation_is_forgotten_when_the_student_asks_something_else():
    agent = make_agent([[_chunk("Thanks.")]])
    await run(agent, "which country is best for me")
    assert agent.memory.profiles[(None, "s1")].get("awaiting") == "recommend_country"
    await run(agent, "hello there")
    assert not agent.memory.profiles[(None, "s1")].get("awaiting")


@pytest.mark.asyncio
async def test_the_first_live_message_with_a_gpa_in_it_is_now_ranked_without_a_budget():
    agent = make_agent([])
    events = await run(agent, OLD_SCREENSHOT_MESSAGE)
    assert kinds(events) == ["profile_summary", "match_cards", "quick_chips"]
    assert agent.memory.profiles[(None, "s1")]["academic_gpa"] == 3
