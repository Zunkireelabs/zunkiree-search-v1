"""While a tenant's catalog is not verified, every card built from its country figures says so, on the card and in its plain-text
version, and the model is told not to state the figures as facts. A verified catalog shows no note. Cards that carry no country
figure (budget, profile, contact form, choices) are left alone."""
import pytest

from app.services.education_catalog import Catalog, get_catalog
from app.services.education_profile import apply_updates, new_profile
from app.services.education_tools import execute_education_tool
from tests.test_education_consistency import make_catalog

NOTE = "Indicative figures for planning, not confirmed Admizz data. A counselor can confirm them."

COUNTRY_FIGURE_CARDS = [
    ("show_country_matches", {}),
    ("show_country_facts", {"country": "uk"}),
    ("compare_countries", {"countries": ["uk", "au"]}),
    ("check_eligibility", {"country": "uk"}),
    ("show_cost_calculator", {"country": "au"}),
]
OTHER_CARDS = [("show_budget_slider", {}), ("show_profile", {}), ("show_lead_form", {}), ("show_choice", {"kind": "countries"}),
               ("show_welcome", {})]


def _catalog(status: str) -> Catalog:
    return Catalog(**{**make_catalog().model_dump(), "status": status})


def _profile() -> dict:
    p = new_profile()
    apply_updates(p, {"countries": ["uk", "au"], "study_level": "master", "budget": 40000, "english_test": "IELTS",
                      "english_score": 6.5, "academic_score": 70})
    return p


@pytest.mark.parametrize("tool,args", COUNTRY_FIGURE_CARDS)
def test_an_unverified_catalog_marks_every_card_that_shows_country_figures(tool, args):
    out = execute_education_tool(tool, dict(args), _profile(), _catalog("PLACEHOLDER"))
    assert out.block is not None
    assert out.block.subtitle == NOTE
    assert out.block.fallback_text.endswith("(Indicative figures, not confirmed.)")
    assert "indicative samples, not confirmed" in out.message and "never state them as facts" in out.message


@pytest.mark.parametrize("tool,args", COUNTRY_FIGURE_CARDS)
def test_a_verified_catalog_shows_no_note(tool, args):
    out = execute_education_tool(tool, dict(args), _profile(), _catalog("verified"))
    assert out.block.subtitle is None
    assert "Indicative" not in out.block.fallback_text and "indicative" not in out.message


@pytest.mark.parametrize("tool,args", OTHER_CARDS)
def test_cards_without_country_figures_are_left_alone(tool, args):
    out = execute_education_tool(tool, dict(args), _profile(), _catalog("PLACEHOLDER"))
    assert out.block is not None and out.block.subtitle != NOTE and "Indicative" not in out.block.fallback_text


def test_the_note_survives_the_block_cache():
    catalog, profile = _catalog("PLACEHOLDER"), _profile()
    first = execute_education_tool("show_country_facts", {"country": "uk"}, profile, catalog).block
    again = execute_education_tool("show_country_facts", {"country": "uk"}, profile, catalog).block
    assert first.subtitle == again.subtitle == NOTE and first.model_dump() == again.model_dump()


def test_the_real_admizz_catalog_is_unverified_so_its_country_cards_carry_the_note():
    catalog = get_catalog("admizz-test")
    assert catalog.is_placeholder
    for tool, args in (("show_country_facts", {"country": "uk"}), ("show_country_facts", {"country": "au"}),
                       ("compare_countries", {"countries": ["uk", "ca"]}), ("show_cost_calculator", {"country": "de"}),
                       ("check_eligibility", {"country": "us"})):
        profile = _profile()
        profile["countries"] = ["uk"]
        block = execute_education_tool(tool, dict(args), profile, catalog).block
        assert block is not None and block.subtitle == NOTE, tool


def test_through_the_agent_a_country_question_streams_the_card_with_its_note():
    import asyncio

    from app.services.education_catalog import register_catalog
    from tests.test_education_agent import make_agent, run

    catalog = _catalog("PLACEHOLDER")
    catalog.site_id = "edu-guard-test"
    register_catalog(catalog)
    agent = make_agent([])        # no scripted reply: the card and its sentence come from code, so any LLM call would fail
    events = asyncio.run(run(agent, "Tell me about the UK", site="edu-guard-test"))
    cards = [e["block"] for e in events if e["type"] == "ui_block" and e["block"]["type"] == "info_card"]
    assert len(cards) == 1 and cards[0]["subtitle"] == NOTE and agent.client.calls == []
