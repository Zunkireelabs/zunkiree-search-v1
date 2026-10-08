"""'Is UK cheaper than Canada?' used to match no rule, so the LLM answered in free text and could invent comparative claims.
Naming two countries and comparing their cost now opens the comparison card, whose rows come from the catalog."""
import pytest

from app.services.education_ui_registry import detect_intent
from tests.test_education_consistency import make_catalog


@pytest.fixture
def catalog():
    return make_catalog()


@pytest.mark.parametrize("question", [
    "Is UK cheaper than Canada?",
    "Which country has cheaper tuition, UK or Canada?",
    "Which is the cheapest, Australia or the UK?",
    "Is Australia more expensive than Canada?",
    "Canada vs UK, which is more affordable",
    "Is the UK less expensive than Australia?",
])
def test_comparing_the_cost_of_two_countries_opens_the_comparison(catalog, question):
    intent, args = detect_intent(question, catalog, {})
    assert intent == "compare" and len(args["countries"]) >= 2


@pytest.mark.parametrize("question", [
    "Is a master's cheaper than a bachelor's?",          # no countries named
    "What is the cheapest option?",
    "Is Canada cheap?",                                  # one country: the existing cost / facts behaviour
])
def test_without_two_countries_it_is_not_a_comparison(catalog, question):
    result = detect_intent(question, catalog, {})
    assert result is None or result[0] != "compare"


def test_the_existing_cost_questions_for_one_country_are_unchanged(catalog):
    assert detect_intent("How much does Canada cost?", catalog, {})[0] == "cost_calculator"
    assert detect_intent("Tuition in Canada", catalog, {})[0] == "cost_calculator"
