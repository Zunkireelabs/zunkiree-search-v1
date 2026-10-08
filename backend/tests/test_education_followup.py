"""Follow-ups on the UI that is on screen: parsing, currency gating, state recording, re-running the same intent,
and the agent flow (same UI type, new data, no LLM tools and no knowledge-base lookup)."""
import pytest

from app.services.education_catalog import Catalog, register_catalog
from app.services.education_followup import (
    catalog_currency_code, extract_slots, parse_amount, record_ui_state, resolve_followup,
)
from app.services.education_memory import InMemoryEducationMemory
from app.services.education_profile import apply_updates, new_profile
from tests.test_education_agent import _chunk, blocks_of, make_agent, run, types
from tests.test_education_consistency import make_catalog


@pytest.fixture
def usd():
    return make_catalog()


@pytest.fixture
def npr():
    return make_catalog().model_copy(update={"currency": "NPR"})


def _on_screen(intent: str, args: dict | None = None, **profile_fields) -> dict:
    p = new_profile()
    apply_updates(p, profile_fields)
    record_ui_state(p, intent, args or {})
    return p


# ---- parsing money ----

@pytest.mark.parametrize("text,value", [
    ("only under 20 lakh", 2_000_000),
    ("around 2.5 lakhs", 250_000),
    ("budget is 1 crore", 10_000_000),
    ("NPR 25 lakh", 2_500_000),
    ("25L", 2_500_000),
    ("$30k", 30_000),
    ("under $30,000", 30_000),
    ("Rs 2000000", 2_000_000),
    ("USD 45000", 45_000),
    ("maximum 40000", 40_000),
    ("1.5m", 1_500_000),
    ("about 25,00,000", 2_500_000),
])
def test_amounts_are_parsed(text, value):
    assert parse_amount(text).value == value


@pytest.mark.parametrize("text", [
    "my IELTS is 6.5",
    "I scored 70%",
    "September 2027 intake",
    "I want to start in 2027",
    "I am 24 years old",
    "50000",                       # a bare number with no cue is not a budget
    "between 30000 and 40000",     # no cue, two numbers: ambiguous, so ignored
    "what is the process to apply?",
])
def test_non_money_is_not_parsed(text):
    assert parse_amount(text) is None


def test_a_bare_large_number_needs_a_cue_word():
    assert parse_amount("budget 50000").value == 50_000
    assert parse_amount("50000") is None


# ---- currency gating: no conversion, nothing guessed ----

def test_lakh_is_applied_only_when_the_catalog_is_nepali_or_indian_rupees(usd, npr):
    assert extract_slots("only under 20 lakh", npr) == {"budget": 2_000_000}
    assert extract_slots("only under 20 lakh", usd) == {}


def test_an_explicit_currency_must_match_the_catalog(usd, npr):
    assert extract_slots("under $30k", usd) == {"budget": 30_000}
    assert extract_slots("under $30k", npr) == {}
    assert extract_slots("under NPR 25 lakh", usd) == {}
    assert extract_slots("under Rs 25 lakh", npr) == {"budget": 2_500_000}


def test_an_amount_with_no_currency_is_taken_in_the_catalog_currency(usd):
    assert extract_slots("budget 35000", usd) == {"budget": 35_000}


@pytest.mark.parametrize("symbol,code", [("$", "USD"), ("£", "GBP"), ("NPR", "NPR"), ("npr", "NPR"), ("₹", "INR")])
def test_catalog_currency_codes(symbol, code):
    assert catalog_currency_code(symbol) == code


# ---- other slots ----

def test_ielts_level_and_intake_are_extracted(usd):
    assert extract_slots("my IELTS is 6.5", usd) == {"english_test": "IELTS", "english_score": 6.5}
    assert extract_slots("I want a master's starting in September", usd) == {"study_level": "master", "intake": "September"}
    assert extract_slots("bachelors", usd) == {"study_level": "bachelor"}


def test_other_english_tests_are_not_read_because_the_catalog_minimums_are_ielts(usd):
    assert extract_slots("my PTE is 65", usd) == {}
    assert extract_slots("IELTS 12", usd) == {}


def test_an_intake_month_the_catalog_does_not_offer_is_ignored(usd):
    assert "intake" not in extract_slots("starting in December", usd)


# ---- ui_state ----

def test_ui_state_records_intent_args_type_and_version():
    p = new_profile()
    record_ui_state(p, "eligibility", {"country": "uk", "goal": "eligibility"})
    assert p["ui_state"] == {"intent": "eligibility", "args": {"country": "uk"}, "ui": {"type": "eligibility_meter", "version": 2}}


def test_input_cards_never_replace_what_is_on_screen():
    p = _on_screen("recommend_country")
    for input_intent in ("choice", "budget", "welcome", "lead_form"):
        record_ui_state(p, input_intent, {})
    assert p["ui_state"]["intent"] == "recommend_country"


@pytest.mark.asyncio
async def test_ui_state_survives_a_memory_round_trip():
    memory = InMemoryEducationMemory()
    await memory.save_profile(None, "s1", _on_screen("recommend_country", budget=30000))
    assert (await memory.load_profile(None, "s1"))["ui_state"]["ui"] == {"type": "match_cards", "version": 2}


def test_a_profile_saved_before_ui_state_existed_still_works(usd):
    legacy = new_profile()
    assert resolve_followup("only under $30k", legacy, usd) is None


# ---- resolving a follow-up ----

def test_a_budget_refinement_reruns_the_same_intent_and_keeps_the_rest_of_the_context(usd):
    profile = _on_screen("recommend_country", budget=40000, study_level="master", countries=["uk", "au"])
    followup = resolve_followup("only show me options under $30k", profile, usd)
    assert (followup.intent, followup.args, followup.updates) == ("recommend_country", {}, {"budget": 30_000})
    assert profile["study_level"] == "master" and profile["countries"] == ["au", "uk"]   # nothing dropped


def test_the_nepali_example_from_the_brief_with_an_npr_catalog(npr):
    profile = _on_screen("recommend_country", budget=2_500_000, study_level="bachelor")
    followup = resolve_followup("Only show universities under 20 lakh", profile, npr)
    assert followup.intent == "recommend_country" and followup.updates == {"budget": 2_000_000}


def test_with_the_usd_catalog_a_lakh_refinement_is_left_to_the_normal_path(usd):
    assert resolve_followup("only under 20 lakh", _on_screen("recommend_country"), usd) is None


def test_a_score_refinement_reruns_recommend_and_eligibility(usd):
    for intent, args in (("recommend_country", {}), ("eligibility", {"country": "uk"})):
        followup = resolve_followup("my IELTS is 7", _on_screen(intent, args), usd)
        assert followup.intent == intent and followup.args == args
        assert followup.updates == {"english_test": "IELTS", "english_score": 7.0}


def test_a_slot_the_shown_ui_does_not_use_does_not_trigger_a_rerun(usd):
    # budget does not feed the eligibility check, so the card on screen would not change
    assert resolve_followup("under $30k", _on_screen("eligibility", {"country": "uk"}), usd) is None
    assert resolve_followup("under $30k", _on_screen("country_facts", {"country": "uk"}), usd) is None


@pytest.mark.parametrize("intent", ["eligibility", "cost_calculator", "country_facts"])
@pytest.mark.parametrize("question,country", [("what about Canada?", "ca"), ("How about Australia", "au"), ("and Canada?", "ca"),
                                              ("ok, what about the UK", "uk")])
def test_what_about_another_country_swaps_the_country_and_keeps_the_intent(usd, intent, question, country):
    followup = resolve_followup(question, _on_screen(intent, {"country": "uk"}), usd)
    assert followup.intent == intent and followup.args == {"country": country} and followup.updates == {}


def test_what_about_needs_exactly_one_country_and_a_country_intent(usd):
    assert resolve_followup("what about Canada and Australia?", _on_screen("eligibility", {"country": "uk"}), usd) is None
    assert resolve_followup("what about the weather?", _on_screen("eligibility", {"country": "uk"}), usd) is None
    assert resolve_followup("what about Canada?", _on_screen("recommend_country"), usd) is None


def test_nothing_on_screen_means_no_followup(usd):
    assert resolve_followup("only under $30k", new_profile(), usd) is None


def test_long_messages_are_not_followups(usd):
    question = "I was thinking about my options and my budget is now around $30k because my family changed plans"
    assert resolve_followup(question, _on_screen("recommend_country"), usd) is None


@pytest.mark.parametrize("question", [
    "What's the budget for Admizz services?",
    "Is the IELTS test hard?",
    "tell me about scholarships",
    "thanks!",
])
def test_unrelated_short_messages_are_left_alone(usd, question):
    assert resolve_followup(question, _on_screen("recommend_country", budget=40000), usd) is None


def test_the_same_followup_on_the_same_state_resolves_identically(usd):
    a = resolve_followup("under $30k", _on_screen("recommend_country", budget=40000), usd)
    b = resolve_followup("under $30k", _on_screen("recommend_country", budget=40000), usd)
    assert a == b


# ---- agent flow ----

@pytest.fixture(autouse=True)
def _agent_catalog():
    cat = make_catalog()
    cat.site_id = "edu-agent-test"
    register_catalog(cat)
    register_catalog(Catalog(site_id="edu-empty"))


def _seed(agent, **fields):
    p = new_profile()
    apply_updates(p, fields)
    agent.memory.profiles[(None, "s1")] = p


@pytest.mark.asyncio
async def test_a_budget_followup_shows_the_same_ui_type_with_new_data_and_no_llm_tools_or_kb_lookup():
    agent = make_agent([[_chunk("Here you go.")], [_chunk("Updated for you.")]])
    _seed(agent, budget=60000, english_score=6.5, academic_score=70)
    [first] = blocks_of(await run(agent, "Which countries fit my profile?"))
    assert first["type"] == "match_cards"

    events = await run(agent, "only under $25k")
    [second] = blocks_of(events)
    assert second["type"] == first["type"] == "match_cards"
    assert second["title"] == first["title"]
    assert second["data"] != first["data"]                           # new data...
    assert "budget" in second["changed_because"]                      # ...and the student is told why
    assert agent.memory.profiles[(None, "s1")]["budget"] == 25_000
    assert "tools" not in agent.client.calls[1]                      # the LLM only wrote the lead-in
    agent.query_service._retrieve_and_rank.assert_not_awaited()
    assert types(events)[-1] == "done"


@pytest.mark.asyncio
async def test_an_ielts_statement_after_a_recommendation_reruns_it():
    agent = make_agent([[_chunk("Here you go.")], [_chunk("Updated.")]])
    _seed(agent, budget=40000, english_score=6.5, academic_score=70)
    await run(agent, "Which countries fit my profile?")
    [second] = blocks_of(await run(agent, "my IELTS is 5.5"))
    p = agent.memory.profiles[(None, "s1")]
    assert second["type"] == "match_cards" and "english score" in second["changed_because"]
    assert p["english_score"] == 5.5 and p["english_test"] == "IELTS"


@pytest.mark.asyncio
async def test_what_about_canada_reruns_eligibility_for_canada_and_tracks_the_new_country():
    agent = make_agent([[_chunk("Here.")], [_chunk("And Canada:")]])
    _seed(agent, english_score=6.5, academic_score=70)
    [uk] = blocks_of(await run(agent, "Am I eligible for the UK?"))
    [ca] = blocks_of(await run(agent, "what about Canada?"))
    assert uk["title"] == "U.K. eligibility" and ca["title"] == "Canada eligibility"
    assert uk["type"] == ca["type"] == "eligibility_meter"
    assert agent.memory.profiles[(None, "s1")]["ui_state"]["args"] == {"country": "ca"}
    assert agent.memory.profiles[(None, "s1")]["focus_country"] == "ca"


@pytest.mark.asyncio
async def test_the_followup_is_remembered_so_a_second_refinement_builds_on_it():
    agent = make_agent([[_chunk("a")], [_chunk("b")], [_chunk("c")]])
    _seed(agent, budget=60000, english_score=6.5, academic_score=70)
    await run(agent, "Which countries fit my profile?")
    await run(agent, "under $30k")
    [third] = blocks_of(await run(agent, "under $20k"))
    assert third["type"] == "match_cards"
    assert agent.memory.profiles[(None, "s1")]["budget"] == 20_000


@pytest.mark.asyncio
async def test_without_a_card_on_screen_a_budget_statement_takes_the_normal_llm_path():
    agent = make_agent([[_chunk("Noted.")]])
    events = await run(agent, "I can spend around $25k")
    assert blocks_of(events) == []
    assert "tools" in agent.client.calls[0]
    agent.query_service._retrieve_and_rank.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_tap_is_never_treated_as_a_followup():
    agent = make_agent([[_chunk("ok")]])
    _seed(agent, budget=60000)
    agent.memory.profiles[(None, "s1")]["ui_state"] = {"intent": "recommend_country", "args": {},
                                                       "ui": {"type": "match_cards", "version": 1}}
    action = {"blockId": "range_slider-x", "blockType": "range_slider", "actionId": "set_value",
              "values": {"field": "budget", "value": 30000}, "displayText": "$30,000 / year"}
    [block] = blocks_of(await run(agent, "$30,000 / year", block_action=action))
    assert block["type"] != "match_cards"          # the guided flow moved on to the next slot instead


@pytest.mark.asyncio
async def test_a_message_with_its_own_explicit_intent_keeps_it_even_if_it_also_states_a_slot():
    agent = make_agent([[_chunk("a")], [_chunk("b")]])
    _seed(agent, budget=40000, english_score=6.5, academic_score=70)
    await run(agent, "Which countries fit my profile?")
    [block] = blocks_of(await run(agent, "Am I eligible for the UK with IELTS 6.5?"))
    assert block["type"] == "eligibility_meter"        # not hijacked into re-running the recommendation


@pytest.mark.asyncio
async def test_plain_about_questions_still_get_country_facts_even_with_a_country_card_on_screen():
    agent = make_agent([[_chunk("a")], [_chunk("b")]])
    _seed(agent, english_score=6.5, academic_score=70)
    await run(agent, "Am I eligible for the UK?")
    [block] = blocks_of(await run(agent, "tell me about Canada"))
    assert block["type"] == "info_card"


@pytest.mark.asyncio
async def test_what_about_with_nothing_on_screen_keeps_todays_facts_behaviour():
    agent = make_agent([[_chunk("a")]])
    [block] = blocks_of(await run(agent, "what about Canada?"))
    assert block["type"] == "info_card"
