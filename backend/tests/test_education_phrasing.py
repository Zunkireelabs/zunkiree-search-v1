"""Phrasing-consistency baseline for the education agent's deterministic intent routing.

Different wordings of the same question must resolve to the same intent and therefore the same
UI block type. This file pins what holds TODAY and documents what does not:

  - plain cases   = phrasings that resolve correctly now (regression guard)
  - xfail(strict) = phrasings that do NOT resolve correctly now. They document known gaps. strict=True
                    means the test fails the moment a gap is fixed, which forces the marker to be removed.

No behavior is fixed here. The intent layer is a later step.
"""
import copy

import pytest

from app.services.education_profile import apply_updates, new_profile
from app.services.education_tools import execute_education_tool, tool_for_intent
from app.services.education_ui_registry import INTENTS, detect_intent
from tests.test_education_consistency import make_catalog

# Becomes "recommend_country" when the intent layer lands; keep the rename to this one line.
RECOMMEND_COUNTRY = "country_matches"


def gap(question: str, reason: str):
    return pytest.param(question, marks=pytest.mark.xfail(strict=True, reason=reason), id=question)


@pytest.fixture
def catalog():
    return make_catalog()


def _profile() -> dict:
    p = new_profile()
    apply_updates(p, {"budget": 40000, "english_score": 6.5, "academic_score": 70})
    return p


# ---- recommend a country ----

RECOMMEND_OK = [
    "What's the best country for me?",
    "Which country should I study in?",
    "Where should I go for my master's?",
    "What country would you recommend?",
    "Where should I study?",
    "Which country is right for me",
]


@pytest.mark.parametrize("question", RECOMMEND_OK)
def test_recommend_country_phrasings_resolve_to_one_intent(catalog, question):
    assert detect_intent(question, catalog, {}) == (RECOMMEND_COUNTRY, {})


@pytest.mark.parametrize("question", [
    gap("Which destination fits my profile?",
        "KNOWN GAP: 'my profile' wins over 'destination', so this shows the profile summary instead of recommendations"),
    gap("Suggest a country for me", "KNOWN GAP: no rule matches, falls through to the LLM"),
    gap("Which destination suits me?", "KNOWN GAP: no rule matches, falls through to the LLM"),
    gap("Recommend a country", "KNOWN GAP: no rule matches, falls through to the LLM"),
])
def test_recommend_country_known_gaps(catalog, question):
    assert detect_intent(question, catalog, {}) == (RECOMMEND_COUNTRY, {})


@pytest.mark.parametrize("variant", [
    "WHICH COUNTRY SHOULD I STUDY IN",
    "  which country should i study in  ",
    "Which country should I study in??",
    gap("which   country   should i study in",
        "KNOWN GAP: runs of spaces inside the sentence are not collapsed, so 'which countr' no longer matches"),
])
def test_case_spacing_and_punctuation_do_not_change_the_intent(catalog, variant):
    assert detect_intent(variant, catalog, {}) == detect_intent("Which country should I study in?", catalog, {})


def test_same_state_different_wording_gives_the_identical_block(catalog):
    """Same meaning + same state -> same UI type and the same block (content-addressed id)."""
    blocks = []
    for question in RECOMMEND_OK:
        intent, args = detect_intent(question, catalog, {})
        outcome = execute_education_tool(tool_for_intent(intent), dict(args), copy.deepcopy(_profile()), catalog)
        assert outcome.block is not None, question
        blocks.append(outcome.block)
    assert {b.type for b in blocks} == {INTENTS[RECOMMEND_COUNTRY].block_type} == {"match_cards"}
    assert len({b.block_id for b in blocks}) == 1
    assert len({b.title for b in blocks}) == 1


# ---- other core intents ----

@pytest.mark.parametrize("question", [
    "Compare UK and Australia",
    "UK or Australia, which is better?",
    "Australia versus Canada",
])
def test_compare_phrasings(catalog, question):
    assert detect_intent(question, catalog, {})[0] == "compare"


@pytest.mark.parametrize("question", [
    gap("how does the UK stack up against Canada", "KNOWN GAP: no compare keyword, falls through to the LLM"),
])
def test_compare_known_gaps(catalog, question):
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
])
def test_country_facts_phrasings(catalog, question):
    assert detect_intent(question, catalog, {})[0] == "country_facts"


@pytest.mark.parametrize("question", [
    gap("What's Australia like?", "KNOWN GAP: no facts keyword, falls through to the LLM"),
])
def test_country_facts_known_gaps(catalog, question):
    assert detect_intent(question, catalog, {})[0] == "country_facts"


# ---- negative controls: these must NOT be claimed by a catalog rule ----

@pytest.mark.parametrize("question", [
    "What's the process to apply?",       # knowledge-base shape, not a catalog card
    "Do I need a visa?",                  # single fact, stays plain text
    "What is the capital of France?",     # off-topic
])
def test_questions_that_are_not_catalog_intents_are_left_alone(catalog, question):
    assert detect_intent(question, catalog, {}) is None
