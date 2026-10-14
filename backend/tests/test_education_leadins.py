"""The sentence that introduces a card is written by code from the card itself (English only). It cannot contradict the card,
offer something we don't have, or twist a fact, and a card reply makes no LLM call at all."""
import json
import re

import pytest

from app.config import Settings
from app.schemas.ui_blocks import build_block
from app.services import education_agent
from app.services.education_catalog import Catalog, CountryRecord, register_catalog
from app.services.education_leadins import KB_FOUND, KB_MISS, leadin_for
from app.services.education_profile import apply_updates, new_profile
from app.services.education_tools import execute_education_tool, tool_for_intent
from tests.test_education_agent import PROCESS_CHUNKS, PROCESS_JSON, _chunk, blocks_of, make_agent, run, types
from tests.test_education_consistency import make_catalog

BRAND = "Admizz"
FULL = dict(budget=40000, english_score=6.5, academic_score=70, intake="September")


def card(intent, args, catalog, **fields):
    p = new_profile()
    apply_updates(p, fields)
    return execute_education_tool(tool_for_intent(intent), dict(args), p, catalog).block


def say(intent, args, catalog, **fields):
    return leadin_for(intent, args, card(intent, args, catalog, **fields), catalog, BRAND)


@pytest.fixture
def catalog():
    return make_catalog()


# ---- each card's sentence ----

def test_welcome_names_the_brand(catalog):
    assert say("welcome", {}, catalog) == "Hi! I'm Admizz's study-abroad assistant. Where would you like to start?"


@pytest.mark.parametrize("kind,expected", [
    ("countries", "Let's start with where you'd like to study."),
    ("study_level", "Got it. Next, what level do you want to study?"),
    ("intake", "Almost there. When would you like to start?"),
    ("country_one", "Which country would you like me to look at?"),
])
def test_guided_questions(catalog, kind, expected):
    assert say("choice", {"kind": kind}, catalog) == expected


def test_budget_profile_and_form(catalog):
    assert say("budget", {}, catalog) == "Next, set your yearly budget (tuition plus living costs)."
    assert say("profile", {}, catalog, **FULL) == "Here's what I know about you so far."
    assert say("lead_form", {}, catalog) == "Please fill in your details below."


def test_country_cards_name_the_country(catalog):
    assert say("country_facts", {"country": "uk"}, catalog) == "Here are the quick facts for U.K."
    assert say("eligibility", {"country": "au"}, catalog, **FULL) == "Here's how your scores compare with Australia's requirements."
    assert say("cost_calculator", {"country": "ca"}, catalog) == "Here's a cost estimate for Canada. Drag the sliders to adjust it."


def test_a_label_ending_in_a_full_stop_never_produces_a_double_one(catalog):
    for intent, args in [("country_facts", {"country": "uk"}), ("cost_calculator", {"country": "uk"}),
                         ("eligibility", {"country": "uk"}), ("compare", {"countries": ["uk", "au"]})]:
        assert ".." not in say(intent, args, catalog, **FULL), intent
    assert say("country_facts", {"country": "uk"}, catalog) == "Here are the quick facts for U.K."
    assert say("cost_calculator", {"country": "uk"}, catalog) == "Here's a cost estimate for U.K. Drag the sliders to adjust it."


def test_comparison_names_two_or_three(catalog):
    assert say("compare", {"countries": ["uk", "au"]}, catalog) == "Here's U.K. and Australia side by side."
    assert say("compare", {"countries": ["uk", "au", "ca"]}, catalog) == "Here's U.K., Australia and Canada side by side."


def test_a_country_card_for_an_unknown_country_has_no_sentence(catalog):
    block = card("country_facts", {"country": "uk"}, catalog)
    assert leadin_for("country_facts", {"country": "atlantis"}, block, catalog, BRAND) is None
    assert leadin_for("country_facts", {}, block, catalog, BRAND) is None


def test_an_unknown_guided_field_or_intent_has_no_sentence(catalog):
    odd = build_block("choice_cards", {"field": "mystery", "multi": False, "options": [{"id": "a", "label": "A"}]}, fallback_text="x")
    assert leadin_for("choice", {}, odd, catalog, BRAND) is None
    assert leadin_for("nonsense", {}, odd, catalog, BRAND) is None


# ---- the sentence always agrees with the card (the bug the live test found) ----

def one_country(**kw) -> Catalog:
    return Catalog(site_id="t", countries=[CountryRecord(**{**dict(
        id="xx", label="Xland", tuition_min=10000, tuition_max=20000, living_min=5000, living_max=10000,
        ielts_min=6.5, academic_min_percent=60, intakes=["September"]), **kw})])


@pytest.mark.parametrize("fields,tier,fragment", [
    (dict(budget=40000, english_score=7, academic_score=70), "strong", "lines up strongly"),
    (dict(budget=40000), "good", "is a good fit so far"),
    (dict(budget=20000, intake="March"), "possible", "Nothing is a clear fit yet; Xland comes closest"),
    (dict(budget=40000, english_score=3), "needs_review", "couldn't find a clear fit"),
])
def test_the_recommendation_sentence_matches_the_top_tier(fields, tier, fragment):
    cat = one_country()
    block = card("recommend_country", {}, cat, **fields)
    assert block.data["items"][0]["tier"] == tier
    assert fragment in leadin_for("recommend_country", {}, block, cat, BRAND)


def test_when_nothing_fits_the_sentence_never_claims_a_match(catalog):
    """The live bug: IELTS 5.5 made every country 'Needs review', but the LLM said 'Canada matches your profile'."""
    block = card("recommend_country", {}, catalog, budget=25000, english_score=5.5, academic_score=70)
    assert {i["tier"] for i in block.data["items"]} == {"needs_review"}
    text = leadin_for("recommend_country", {}, block, catalog, BRAND)
    assert "match" not in text.lower() and "strong" not in text.lower() and "good fit" not in text.lower()
    assert not any(i["label"] in text for i in block.data["items"])          # it does not single a country out


# ---- nothing risky can ever be said ----

FORBIDDEN = re.compile(r"\b(best|guarantee|universit\w*|programs?|courses?|approval|will (call|contact|email))\b|%|\d", re.I)


def test_no_sentence_makes_a_risky_claim(catalog):
    sentences = [KB_FOUND, KB_MISS]
    cases = [("welcome", {}), ("budget", {}), ("profile", {}), ("lead_form", {}), ("choice", {"kind": "countries"}),
             ("choice", {"kind": "study_level"}), ("choice", {"kind": "intake"}), ("choice", {"kind": "country_one"}),
             ("compare", {"countries": ["uk", "au", "ca"]}), ("country_facts", {"country": "uk"}),
             ("eligibility", {"country": "uk"}), ("cost_calculator", {"country": "uk"}), ("recommend_country", {})]
    for fields in (FULL, dict(budget=40000), dict(budget=25000, english_score=3), dict(budget=20000, intake="March")):
        for intent, args in cases:
            block = card(intent, args, catalog, **fields)
            if block:
                sentences.append(leadin_for(intent, args, block, catalog, BRAND))
    assert all(sentences) and len(set(sentences)) > 10
    for s in sentences:
        assert not FORBIDDEN.search(s.replace("Admizz's", "")), s


# ---- the agent: card replies make no LLM call ----

@pytest.fixture(autouse=True)
def _agent_catalog():
    from app.services import education_kb_blocks
    education_kb_blocks._llm_shape_cache.clear()      # the knowledge-base caches are shared across tests
    education_kb_blocks._shared_cache.clear()
    cat = make_catalog()
    cat.site_id = "edu-agent-test"
    register_catalog(cat)


def seed(agent, **fields):
    p = new_profile()
    apply_updates(p, fields)
    agent.memory.profiles[(None, "s1")] = p


def streamed_text(events):
    return "".join(e["data"] for e in events if e["type"] == "token")


@pytest.mark.asyncio
async def test_a_recommendation_turn_makes_no_llm_call_and_says_what_the_code_wrote():
    agent = make_agent([])                       # an empty script: any LLM call would fail the test
    seed(agent, **FULL)
    events = await run(agent, "Which countries fit my profile?")
    assert agent.client.calls == []
    assert [b["type"] for b in blocks_of(events)] == ["profile_summary", "match_cards", "quick_chips"]
    assert streamed_text(events) == "U.K. lines up strongly with what you've told me. Here's how all the countries compare."
    assert events[-1]["type"] == "done" and events[-1]["answer"] == streamed_text(events)


@pytest.mark.asyncio
async def test_the_sentence_is_saved_with_the_message_so_a_reload_shows_it():
    agent = make_agent([])
    seed(agent, **FULL)
    await run(agent, "Which countries fit my profile?")
    [_, assistant] = await agent.memory.list_messages(None, "s1")
    assert assistant["content"] == "U.K. lines up strongly with what you've told me. Here's how all the countries compare."


@pytest.mark.asyncio
async def test_the_greeting_and_the_guided_steps_need_no_llm():
    agent = make_agent([])
    welcome = await run(agent, "hi")
    assert streamed_text(welcome) == "Hi! I'm Admizz's study-abroad assistant. Where would you like to start?"
    tile = blocks_of(welcome)[0]
    action = {"blockId": tile["block_id"], "blockType": "journey_cards", "actionId": "start", "values": {"journey": "find"},
              "displayText": "Find the right country"}
    assert streamed_text(await run(agent, "Find the right country", block_action=action)) == "Let's start with where you'd like to study."
    assert agent.client.calls == []


@pytest.mark.asyncio
async def test_buttons_and_follow_ups_are_templated_too():
    agent = make_agent([])
    seed(agent, **FULL)
    first = await run(agent, "Which countries fit my profile?")
    chips = next(b for b in blocks_of(first) if b["type"] == "quick_chips")
    tap = {"blockId": chips["block_id"], "blockType": "quick_chips", "actionId": "eligibility:uk", "values": {},
           "displayText": "Check my eligibility for U.K."}
    assert streamed_text(await run(agent, "x", block_action=tap)) == "Here's how your scores compare with U.K.'s requirements."
    assert streamed_text(await run(agent, "what about Canada?")) == "Here's how your scores compare with Canada's requirements."
    assert agent.client.calls == []


@pytest.mark.asyncio
async def test_a_card_where_nothing_fits_does_not_claim_a_match():
    agent = make_agent([])
    seed(agent, budget=25000, english_score=5.5, academic_score=70)
    events = await run(agent, "Which countries fit my profile?")
    text = streamed_text(events)
    assert "couldn't find a clear fit" in text and "match" not in text.lower()


@pytest.mark.asyncio
async def test_a_knowledge_base_card_is_introduced_by_code_after_one_extraction_call():
    agent = make_agent([PROCESS_JSON], chunks=PROCESS_CHUNKS)
    events = await run(agent, "What is the application process?")
    assert [b["type"] for b in blocks_of(events)] == ["stepper"]
    assert streamed_text(events) == KB_FOUND
    assert len(agent.client.calls) == 1            # the extraction only; no lead-in call


@pytest.mark.asyncio
async def test_a_knowledge_base_miss_says_it_has_no_such_detail_and_points_to_the_counselor_button():
    agent = make_agent([json.dumps({"found": False})], chunks=PROCESS_CHUNKS)
    events = await run(agent, "What is the application process?")
    assert streamed_text(events) == KB_MISS and "I don't have that detail" in KB_MISS
    assert [b["type"] for b in blocks_of(events)] == ["quick_chips"]
    assert len(agent.client.calls) == 1


@pytest.mark.asyncio
async def test_without_the_counselor_button_a_miss_still_goes_to_the_llm(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_compositions", False)
    agent = make_agent([json.dumps({"found": False}), [_chunk("I don't have those details; a counselor can help.")]], chunks=PROCESS_CHUNKS)
    events = await run(agent, "What is the application process?")
    assert blocks_of(events) == [] and "tools" in agent.client.calls[1]


# ---- when code does NOT write the sentence ----

@pytest.mark.asyncio
async def test_a_message_in_another_language_keeps_the_llm_written_lead_in():
    agent = make_agent([[_chunk("Yo hamro sujhaav ho.")]])
    seed(agent, **FULL)
    events = await run(agent, "Which countries fit my profile, malai batayo?")
    assert [b["type"] for b in blocks_of(events)] == ["profile_summary", "match_cards", "quick_chips"]
    assert streamed_text(events) == "Yo hamro sujhaav ho." and len(agent.client.calls) == 1


@pytest.mark.asyncio
async def test_free_text_turns_still_use_the_llm():
    agent = make_agent([[_chunk("Noted, thanks!")]])
    events = await run(agent, "I have a question about my cousin")
    assert streamed_text(events) == "Noted, thanks!" and len(agent.client.calls) == 1


@pytest.mark.asyncio
async def test_with_the_switch_off_the_llm_writes_the_lead_in_again(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_template_leadins", False)
    agent = make_agent([[_chunk("Here you go.")]])
    seed(agent, **FULL)
    events = await run(agent, "Which countries fit my profile?")
    assert streamed_text(events) == "Here you go." and len(agent.client.calls) == 1


def test_templated_lead_ins_are_on_by_default():
    assert Settings.model_fields["education_template_leadins"].default is True
