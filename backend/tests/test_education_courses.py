"""Universities and courses: the search, the two cards, how a question or a tap reaches them, and the promises around fees.

A catalog without courses must behave exactly as before (no new intent fires), and nothing is ever invented: a fee the source
does not state as a plain figure is shown in the source's own words, never as a number we computed."""
import pytest

from app.schemas.ui_blocks import UI_TYPES, build_block
from app.services.education_actions import validate_block_action
from app.services.education_agent import _turn_intent
from app.services.education_catalog import Catalog
from app.services.education_catalog_models import Course, University
from app.services.education_catalog_search import (
    CourseQuery, level_in_text, pick_results, search_courses, subject_terms, universities_in_text,
)
from app.services.education_compositions import compose, chip_intent, normalized_args
from app.services.education_leadins import leadin_for
from app.services.education_profile import new_profile
from app.services.education_tools import execute_education_tool
from app.services.education_ui_registry import detect_intent
from app.services.money import Money
from tests.test_education_consistency import make_catalog


def _course(cid, uni, name, level="master", fee=None, **kw):
    return Course(id=cid, university_id=uni, name=name, level=level, tuition_per_year=Money(fee, "GBP") if fee else None,
                  duration_months=kw.pop("duration_months", 12), intakes=kw.pop("intakes", ["January"]), **kw)


def make_course_catalog(status: str = "PLACEHOLDER") -> Catalog:
    base = make_catalog()
    return Catalog(
        site_id="edu-test", currency="$", status=status, countries=base.countries,
        universities=[
            University(id="arden-university", name="Arden University", country_id="uk", city="London", intakes=["January"]),
            University(id="aston-university", name="Aston University", country_id="uk", city="Birmingham"),
            University(id="aston-university-oncampus", name="Aston University – OnCampus (UG pathway)", country_id="uk", city="Birmingham"),
            University(id="university-of-essex", name="University of Essex", country_id="uk", city="Colchester"),
            University(id="uni-au", name="Sydney Test University", country_id="au", city="Sydney"),
        ],
        courses=[
            _course("a1", "arden-university", "MSc Data Science", fee=14000, ielts_min=6.0, academic_min_percent=55),
            _course("a2", "arden-university", "MBA", fee=14000, ielts_min=6.0),
            _course("a3", "arden-university", "BSc (Hons) Computing (Top-Up)", level="bachelor", fee=12500, ielts_min=6.0),
            _course("s1", "aston-university", "MSc Data Science and Analytics", fee=19000),
            _course("e1", "university-of-essex", "MSc Data Science", fee=24675),
            _course("e2", "university-of-essex", "LLM Law", fee=24675),
            _course("o1", "aston-university-oncampus", "BSc Business with Foundation Year", level="foundation", duration_months=48,
                    tuition_total=Money(60000, "GBP"), tuition_note="then £1,000 more"),
            _course("n1", "aston-university", "MSc Nursing", tuition_note="from £9,400 per year · £9,400–£17,700 depending on course"),
            _course("x1", "uni-au", "Master of Data Science", fee=30000),
        ])


@pytest.fixture
def catalog():
    return make_course_catalog()


# ---- search ----

def test_subject_words_level_and_named_university_are_read_from_the_question(catalog):
    q = "MSc data science at the University of Essex"
    uni = universities_in_text(catalog, q)
    assert uni == ["university-of-essex"] and subject_terms(q, catalog, uni) == ("msc", "data", "science") and level_in_text(q) == "master"


def test_longer_university_name_wins_over_the_name_it_contains(catalog):
    assert universities_in_text(catalog, "courses at aston university oncampus") == ["aston-university-oncampus"]
    assert universities_in_text(catalog, "courses at aston university") == ["aston-university"]


def test_degree_abbreviations_are_search_terms_and_short_terms_match_whole_words(catalog):
    assert [c.id for c in search_courses(catalog, CourseQuery(terms=("mba",)))] == ["a2"]
    assert search_courses(catalog, CourseQuery(terms=("ba",))) == []          # not a piece of "Analytics" / "Business"


def test_search_filters_and_orders_by_the_cheapest_stated_yearly_fee(catalog):
    ids = [c.id for c in search_courses(catalog, CourseQuery(country="uk", level="master", terms=("data", "science")))]
    assert ids == ["a1", "s1", "e1"]                                           # the Australian course is outside the country
    assert [c.id for c in search_courses(catalog, CourseQuery(university="arden-university"))] == ["a3", "a2", "a1"]      # equal fees: by name
    unpriced_last = [c.id for c in search_courses(catalog, CourseQuery(country="uk", level="master"))]
    assert unpriced_last[-1] == "n1"                                           # a course with no yearly figure comes after the priced ones


def test_a_broad_search_shows_one_course_per_university(catalog):
    found = search_courses(catalog, CourseQuery(country="uk", terms=("data", "science")))
    assert [c.university_id for c in pick_results(found, one_per_university=True)] == ["arden-university", "aston-university", "university-of-essex"]


# ---- the course results card ----

def test_course_results_card_is_built_from_the_catalog_and_says_fees_can_change(catalog):
    out = execute_education_tool("show_course_results", {"query": "data science", "level": "master", "country": "uk"}, new_profile(), catalog)
    block = out.block
    assert block.type == "course_results" and block.title == "Courses that match"
    assert block.subtitle == "Fees come from Admizz's website and can change. A counselor can confirm them."
    d = block.data
    assert (d["total"], d["universities"], len(d["items"])) == (3, 3, 3)
    first = d["items"][0]
    assert (first["name"], first["university"], first["fee"], first["duration"], first["intakes"], first["ielts"]) == (
        "MSc Data Science", "Arden University", "£14,000 / year", "1 year", "January", "IELTS 6")
    assert d["filters"] == ["Master's", "Data Science", "U.K.", "Lowest fee first"]
    assert execute_education_tool("show_course_results", {"query": "msc data science"}, new_profile(), catalog).block.data["filters"][1] == "MSc Data Science"
    assert detect_intent("Can you recommend a university for computer science", catalog) == ("courses", {"query": "computer science"})
    assert "never quote a fee" in out.message and "can change" in out.message


def test_the_fees_can_change_line_stays_on_a_verified_catalog_too():
    block = execute_education_tool("show_course_results", {"query": "law"}, new_profile(), make_course_catalog("verified")).block
    assert block.subtitle and "can change" in block.subtitle


def test_fees_are_shown_as_the_source_states_them_never_computed(catalog):
    items = {i["course_id"]: i for i in execute_education_tool("show_course_results", {"university": "aston-university"},
                                                               new_profile(), catalog).block.data["items"]}
    assert items["n1"]["fee"] == "from £9,400 per year · £9,400–£17,700 depending on course"
    total = execute_education_tool("show_course_results", {"university": "aston-university-oncampus"}, new_profile(), catalog).block
    assert total.data["items"][0]["fee"] == "£60,000 total" and total.data["items"][0]["duration"] == "4 years"


def test_a_search_with_no_match_builds_nothing_and_tells_the_model_not_to_suggest_one(catalog):
    out = execute_education_tool("show_course_results", {"query": "astrophysics"}, new_profile(), catalog)
    assert out.block is None and "do not suggest one" in out.message
    assert execute_education_tool("show_course_results", {"university": "Nowhere Uni"}, new_profile(), catalog).block is None


def test_the_level_from_the_profile_is_used_but_dropped_if_it_leaves_nothing(catalog):
    profile = new_profile()
    profile["study_level"] = "phd"
    block = execute_education_tool("show_course_results", {"query": "law"}, profile, catalog).block
    assert block is not None and "PhD" not in block.data["filters"]


def test_a_catalog_without_courses_builds_nothing(catalog):
    assert execute_education_tool("show_course_results", {}, new_profile(), make_catalog()).block is None
    assert execute_education_tool("show_university", {"university": "Arden"}, new_profile(), make_catalog()).block is None


# ---- the university card ----

def test_university_card_states_only_what_the_catalog_has(catalog):
    block = execute_education_tool("show_university", {"university": "Arden University"}, new_profile(), catalog).block
    assert block.type == "university_card" and block.title == "Arden University"
    rows = {r["label"]: r["value"] for r in block.data["rows"]}
    assert rows["Location"] == "London" and rows["Intakes"] == "January"
    assert rows["Courses"] == "3 (1 bachelor's, 2 master's)"
    assert rows["Tuition"] == "£12,500–£14,000 / year" and rows["English requirement"] == "IELTS 6" and rows["Academic requirement"] == "55%"
    assert rows["Source"] == "Admizz website"


def test_university_card_leaves_out_what_it_does_not_know(catalog):
    rows = {r["label"] for r in execute_education_tool("show_university", {"university": "University of Essex"}, new_profile(), catalog).block.data["rows"]}
    assert "English requirement" not in rows and "Academic requirement" not in rows and "Intakes" not in rows


def test_the_same_question_gives_the_identical_card(catalog):
    profile = new_profile()
    first = execute_education_tool("show_course_results", {"query": "law"}, profile, catalog).block
    second = execute_education_tool("show_course_results", {"query": "law"}, profile, catalog).block
    assert first.model_dump() == second.model_dump()


# ---- from a question or a tap to a card ----

@pytest.mark.parametrize("question,intent,args", [
    ("Tell me about Arden University", "university", {"university": "arden-university"}),
    ("arden university", "university", {"university": "arden-university"}),
    ("What courses does the University of Essex have?", "courses", {"university": "university-of-essex"}),
    ("MSc data science in the UK", "courses", {"country": "uk", "query": "msc data science", "level": "master"}),
    ("which universities offer law", "courses", {"query": "law"}),
    ("masters in nursing", "courses", {"query": "nursing", "level": "master"}),
    ("what are the fees for the MBA", "courses", {"query": "mba", "level": "master"}),
])
def test_questions_reach_the_right_card(catalog, question, intent, args):
    assert detect_intent(question, catalog) == (intent, args)


@pytest.mark.parametrize("question", ["Which countries fit my profile?", "compare UK and Australia", "how much does it cost to study in the UK",
                                      "check my eligibility for the UK", "hi", "talk to a counselor", "Tell me about the UK"])
def test_other_questions_keep_their_old_cards_even_with_courses_in_the_catalog(catalog, question):
    intent = detect_intent(question, catalog)
    assert intent is not None and intent[0] not in ("courses", "university")


@pytest.mark.parametrize("question", ["Tell me about Arden University", "MSc data science in the UK", "which universities offer law", "I want an MBA"])
def test_a_catalog_without_courses_never_reaches_the_new_cards(question):
    intent = detect_intent(question, make_catalog())
    assert intent is None or intent[0] not in ("courses", "university")


def test_two_named_universities_are_left_to_the_other_rules(catalog):
    assert detect_intent("Arden University or University of Essex", catalog) is None


def test_tapping_a_course_opens_that_university(catalog):
    block = execute_education_tool("show_course_results", {"query": "law"}, new_profile(), catalog).block
    tap = {"blockId": block.block_id, "blockType": "course_results", "actionId": "open_university",
           "values": {"university_id": "university-of-essex"}}
    assert validate_block_action(tap, block.model_dump()) is None
    assert _turn_intent("Tell me about University of Essex", tap, catalog, new_profile()) == ("university", {"university": "university-of-essex"})


def test_a_tap_for_a_university_that_is_not_on_the_card_is_refused(catalog):
    block = execute_education_tool("show_course_results", {"query": "law"}, new_profile(), catalog).block
    tap = {"blockId": block.block_id, "blockType": "course_results", "actionId": "open_university", "values": {"university_id": "arden-university"}}
    assert validate_block_action(tap, block.model_dump()) == "not_an_option"
    assert _turn_intent("x", {**tap, "values": {"university_id": "made-up"}}, catalog, new_profile()) is None


# ---- companions, buttons and the sentence ----

def test_a_university_shows_its_facts_then_its_courses_then_a_counselor_button(catalog):
    profile = new_profile()
    primary = execute_education_tool("show_university", {"university": "arden-university"}, profile, catalog).block
    blocks = compose("university", {"university": "arden-university"}, primary, profile, catalog)
    assert [b.type for b in blocks] == ["university_card", "course_results", "quick_chips"]
    assert {i["university_id"] for i in blocks[1].data["items"]} == {"arden-university"}
    assert [c["id"] for c in blocks[2].data["chips"]] == ["lead"]


def test_country_facts_offer_a_courses_button_only_where_courses_exist(catalog):
    profile = new_profile()
    uk = execute_education_tool("show_country_facts", {"country": "uk"}, profile, catalog).block
    assert "courses:uk" in [c["id"] for c in compose("country_facts", {"country": "uk"}, uk, profile, catalog)[-1].data["chips"]]
    ca = execute_education_tool("show_country_facts", {"country": "ca"}, profile, catalog).block
    assert not any(c["id"] == "courses:ca" for c in compose("country_facts", {"country": "ca"}, ca, profile, catalog)[-1].data["chips"])
    assert chip_intent("courses:uk", catalog) == ("courses", {"country": "uk"})


def test_tool_arguments_from_the_model_are_normalised(catalog):
    assert normalized_args("courses", {"country": "UK", "university": "Arden", "query": " law ", "level": "master", "junk": 1}, catalog) == {
        "country": "uk", "university": "arden-university", "query": "law", "level": "master"}
    assert normalized_args("university", {"university": "essex"}, catalog) == {"university": "university-of-essex"}
    assert normalized_args("university", {"university": "nobody"}, catalog) == {}


def test_the_sentence_is_written_from_the_card(catalog):
    profile = new_profile()
    many = execute_education_tool("show_course_results", {"query": "data science", "country": "uk"}, profile, catalog).block
    assert leadin_for("courses", {}, many, catalog, "Admizz") == "Here are the 3 matching courses."
    big = Catalog(**{**catalog.model_dump(), "courses": catalog.model_dump()["courses"] + [
        _course(f"z{i}", "arden-university", f"MSc Extra {i}", fee=15000 + i).model_dump() for i in range(8)]})
    block = execute_education_tool("show_course_results", {"university": "arden-university"}, profile, big).block
    assert leadin_for("courses", {}, block, big, "Admizz") == "Here are 6 of the 11 matching courses, across 1 university."
    uni = execute_education_tool("show_university", {"university": "arden-university"}, profile, catalog).block
    assert leadin_for("university", {}, uni, catalog, "Admizz") == "Here's what we have on Arden University."
    for text in (leadin_for("courses", {}, block, big, "Admizz"), leadin_for("university", {}, uni, catalog, "Admizz")):
        assert not any(w in text.lower() for w in ("best", "cheapest", "guarantee", "%"))


def test_blocks_are_registered_and_built_through_the_validated_builder():
    assert {"course_results", "university_card"} <= set(UI_TYPES)
    with pytest.raises(Exception):
        build_block("course_results", {"total": 1, "universities": 1, "items": []}, fallback_text="x")
    with pytest.raises(Exception):
        build_block("course_results", {"total": 0, "universities": 1, "items": [{"course_id": "c", "name": "n", "level_label": "l",
                    "university_id": "u", "university": "U"}]}, fallback_text="x")


# ---- through the real agent turn (fake LLM: none of these cards needs it) ----

import asyncio  # noqa: E402

from app.services.education_catalog import register_catalog  # noqa: E402
from tests.test_education_agent import _chunk, make_agent, run  # noqa: E402


def _turn(agent, question, **kw):
    events = asyncio.run(run(agent, question, site="edu-courses-test", **kw))
    blocks = [e["block"] for e in events if e["type"] == "ui_block"]
    text = "".join(e["data"] for e in events if e["type"] == "token")
    return blocks, text


def test_a_course_question_streams_the_course_card_and_a_sentence_written_by_code():
    cat = make_course_catalog()
    cat.site_id = "edu-courses-test"
    register_catalog(cat)
    agent = make_agent([])                       # an empty script: any LLM call would fail the test
    blocks, text = _turn(agent, "MSc data science in the UK")
    assert [b["type"] for b in blocks] == ["course_results", "quick_chips"]
    assert text == "Here are the 3 matching courses." and agent.client.calls == []
    assert [i["university"] for i in blocks[0]["data"]["items"]] == ["Arden University", "Aston University", "University of Essex"]


def test_tapping_a_course_opens_its_university_through_the_agent():
    cat = make_course_catalog()
    cat.site_id = "edu-courses-test"
    register_catalog(cat)
    agent = make_agent([])
    blocks, _ = _turn(agent, "MSc data science in the UK")
    card = blocks[0]
    tap = {"blockId": card["block_id"], "blockType": "course_results", "actionId": "open_university",
           "values": {"university_id": "university-of-essex"}}
    after, text = _turn(agent, "Tell me about University of Essex", block_action=tap)
    assert [b["type"] for b in after] == ["university_card", "course_results", "quick_chips"]
    assert after[0]["title"] == "University of Essex" and text == "Here's what we have on University of Essex."
    assert {i["university_id"] for i in after[1]["data"]["items"]} == {"university-of-essex"}
    forged = {**tap, "values": {"university_id": "uni-au"}}          # a university that is not on that card: dropped, the typed text decides
    assert validate_block_action(forged, card) == "not_an_option"


def test_a_tenant_without_courses_gets_no_course_card_from_the_same_question():
    cat = make_catalog()
    cat.site_id = "edu-courses-test"
    register_catalog(cat)
    blocks, _ = _turn(make_agent(['{"shape": "none"}', [_chunk("I don't have that detail, but a counselor can help.")]]), "Tell me about Arden University")
    assert not any(b["type"] in ("course_results", "university_card") for b in blocks)
