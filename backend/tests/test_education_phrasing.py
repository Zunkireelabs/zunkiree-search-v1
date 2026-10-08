"""Phrasing-consistency suite for the education agent's deterministic intent routing.

Different wordings of the same question must resolve to the same intent and therefore the same UI block type.
Negative controls guard the other direction: look-alike questions that are NOT catalog intents must stay unrouted
(they go to the knowledge base / LLM path), so widening a rule never swallows an unrelated question."""
import copy

import pytest

from app.services.education_profile import apply_updates, new_profile
from app.services.education_tools import execute_education_tool, tool_for_intent
from app.services.education_ui_registry import INTENTS, detect_intent
from tests.test_education_consistency import make_catalog

RECOMMEND_COUNTRY = "recommend_country"


@pytest.fixture
def catalog():
    return make_catalog()


def _profile() -> dict:
    p = new_profile()
    apply_updates(p, {"budget": 40000, "english_score": 6.5, "academic_score": 70})
    return p


# ---- recommend a country ----

RECOMMEND_PHRASINGS = [
    "What's the best country for me?",
    "Which country should I study in?",
    "Where should I go for my master's?",
    "Which destination fits my profile?",
    "What country would you recommend?",
    "Where should I study?",
    "Which country is right for me",
    "Suggest a country for me",
    "Which destination suits me?",
    "Recommend a country",
    "Can you recommend a destination for my master's?",
    "What destinations suit my budget?",
    "Which countries match my profile?",
]


@pytest.mark.parametrize("question", RECOMMEND_PHRASINGS)
def test_recommend_country_phrasings_resolve_to_one_intent(catalog, question):
    assert detect_intent(question, catalog, {}) == (RECOMMEND_COUNTRY, {})


@pytest.mark.parametrize("variant", [
    "WHICH COUNTRY SHOULD I STUDY IN",
    "  which country should i study in  ",
    "Which country should I study in??",
    "which   country   should i study in",
    "Which\tcountry\nshould I study in?",
])
def test_case_spacing_and_punctuation_do_not_change_the_intent(catalog, variant):
    assert detect_intent(variant, catalog, {}) == detect_intent("Which country should I study in?", catalog, {})


def test_same_state_different_wording_gives_the_identical_block(catalog):
    """Same meaning + same state -> same UI type and the same block (content-addressed id)."""
    blocks = []
    for question in RECOMMEND_PHRASINGS:
        intent, args = detect_intent(question, catalog, {})
        outcome = execute_education_tool(tool_for_intent(intent), dict(args), copy.deepcopy(_profile()), catalog)
        assert outcome.block is not None, question
        blocks.append(outcome.block)
    assert {b.type for b in blocks} == {INTENTS[RECOMMEND_COUNTRY].block_type} == {"match_cards"}
    assert len({b.block_id for b in blocks}) == 1
    assert len({b.title for b in blocks}) == 1


def test_a_known_profile_does_not_change_which_intent_a_question_resolves_to(catalog):
    for question in RECOMMEND_PHRASINGS:
        assert detect_intent(question, catalog, _profile()) == (RECOMMEND_COUNTRY, {}), question


# ---- other core intents ----

@pytest.mark.parametrize("question", [
    "Compare UK and Australia",
    "UK or Australia, which is better?",
    "Australia versus Canada",
    "how does the UK stack up against Canada",
    "What's the difference between the UK and Australia?",
])
def test_compare_phrasings(catalog, question):
    assert detect_intent(question, catalog, {})[0] == "compare"


@pytest.mark.parametrize("question", [
    "Am I eligible for Australia?",
    "Do I qualify for the UK?",
    "What are my chances in Canada?",
    "Can I get into Canada?",
])
def test_eligibility_phrasings(catalog, question):
    assert detect_intent(question, catalog, {})[0] == "eligibility"


@pytest.mark.parametrize("question", [
    "How much does Canada cost?",
    "What are the fees in the UK?",
    "Can I afford Australia?",
    "Tuition in Canada",
])
def test_cost_phrasings(catalog, question):
    assert detect_intent(question, catalog, {})[0] == "cost_calculator"


@pytest.mark.parametrize("question", [
    "Tell me about the UK",
    "UK quick facts",
    "What's Australia like?",
    "What is Canada like?",
])
def test_country_facts_phrasings(catalog, question):
    assert detect_intent(question, catalog, {})[0] == "country_facts"


# ---- negative controls: look-alikes that must NOT be claimed by a catalog rule ----

@pytest.mark.parametrize("question", [
    "What's the process to apply?",          # knowledge-base shape, not a catalog card
    "Do I need a visa?",                     # single fact, stays plain text
    "What is the capital of France?",        # off-topic
    "Can you recommend a good restaurant?",  # 'recommend' without a country/destination
    "Suggest a movie for me",
    "What's the weather like?",              # 'like' without a country
    "What is life like in Nepal?",           # a country we don't list
    "Is Admizz free?",
    "How much does Admizz charge?",          # about the company, not study costs
    "Can I apply through Admizz?",
    "What's the difference between a bachelor's and a master's?",   # 'difference' without two countries
    "What's your recommendation process like?",
    "Which documents do I need?",
])
def test_questions_that_are_not_catalog_intents_are_left_alone(catalog, question):
    assert detect_intent(question, catalog, {}) is None
