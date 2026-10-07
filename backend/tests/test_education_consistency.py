"""Consistency guarantees for the education generative-UI agent:
same question -> same block type/title, unchanged profile -> identical block,
changed profile -> same block type with an explanation, no data -> no invented card."""
import pytest

from app.schemas.ui_blocks import BlockValidationError, build_block
from app.services.education_catalog import Catalog, CountryRecord, score_countries
from app.services.education_profile import apply_block_action, apply_updates, new_profile
from app.services.education_tools import execute_education_tool
from app.services.education_ui_registry import INTENTS, TOOL_TO_INTENT, detect_intent


def make_catalog() -> Catalog:
    return Catalog(site_id="edu-test", currency="$", countries=[
        CountryRecord(id="uk", label="U.K.", aliases=["UK", "United Kingdom"], icon="UK",
                      tuition_min=15000, tuition_max=25000, living_min=10000, living_max=14000,
                      ielts_min=6.5, academic_min_percent=60, intakes=["September"], post_study_visa="2 years"),
        CountryRecord(id="au", label="Australia", aliases=["Aus"], icon="AU",
                      tuition_min=20000, tuition_max=35000, living_min=18000, living_max=24000,
                      ielts_min=6.0, academic_min_percent=55, intakes=["February", "July"],
                      funds_required="A$29,710 living costs"),
        CountryRecord(id="ca", label="Canada", icon="CA",
                      tuition_min=15000, tuition_max=30000, living_min=12000, living_max=15000, ielts_min=6.0),
    ])


@pytest.fixture
def catalog():
    return make_catalog()


@pytest.fixture
def profile():
    p = new_profile()
    apply_updates(p, {"budget": 40000, "english_score": 6.5, "academic_score": 70})
    return p


# ---- question -> intent map ----

@pytest.mark.parametrize("question,intent", [
    ("Which countries fit my profile?", "country_matches"),   # contains "my profile": must NOT be 'profile'
    ("which country is applicable for my profile", "country_matches"),
    ("What countries suit me?", "country_matches"),
    ("best countries for me", "country_matches"),
    ("What do you know about me", "profile"),
    ("show my profile", "profile"),
    ("UK vs Australia?", "compare"),
    ("compare UK and Australia", "compare"),
    ("Can I qualify for Australia?", "eligibility"),
    ("Am I eligible for the UK", "eligibility"),
    ("How much will it cost?", "choice"),                 # no country known: ask which one (sets a goal)
    ("how much does Australia cost", "cost_calculator"),
    ("Am I eligible?", "choice"),
    ("hello", "welcome"),
    ("Hi!", "welcome"),
    ("tell me about Canada", "country_facts"),
    ("I want to study abroad", "choice"),
    ("I want to talk to a counselor", "lead_form"),
])
def test_core_questions_map_to_fixed_intent(catalog, question, intent):
    assert detect_intent(question, catalog)[0] == intent


def test_unrecognised_text_goes_to_llm(catalog):
    assert detect_intent("my IELTS is 6.5", catalog) is None
    assert detect_intent("how much does Admizz charge?", catalog) is None   # about the company, not study costs
    assert detect_intent("can I apply through Admizz?", catalog) is None
    assert detect_intent("what's the weather", catalog) is None


def test_registry_is_one_to_one():
    assert len({s.tool for s in INTENTS.values()}) == len(INTENTS)
    assert len({s.block_type for s in INTENTS.values()}) == len(INTENTS)
    assert set(TOOL_TO_INTENT) == {s.tool for s in INTENTS.values()}


# ---- same question, same UI ----

def test_asking_twice_with_unchanged_profile_gives_identical_block(catalog, profile):
    first = execute_education_tool("show_country_matches", {}, profile, catalog).block
    # unrelated activity in between
    execute_education_tool("show_country_facts", {"country": "au"}, profile, catalog)
    execute_education_tool("show_profile", {}, profile, catalog)
    second = execute_education_tool("show_country_matches", {}, profile, catalog).block

    assert first == second
    assert second.type == "match_cards"
    assert second.title == "Countries that match your profile"
    assert second.changed_because is None


def test_unrelated_profile_change_does_not_disturb_the_block(catalog, profile):
    first = execute_education_tool("show_country_matches", {}, profile, catalog).block
    apply_updates(profile, {"field_of_study": "IT"})  # not an input to country matching
    second = execute_education_tool("show_country_matches", {}, profile, catalog).block
    assert first == second


def test_changed_profile_keeps_block_type_and_title_and_explains(catalog, profile):
    first = execute_education_tool("show_country_matches", {}, profile, catalog).block
    apply_updates(profile, {"english_score": 5.0})
    second = execute_education_tool("show_country_matches", {}, profile, catalog).block

    assert (second.type, second.title) == (first.type, first.title)
    assert second.data != first.data
    assert "english score" in second.changed_because


def test_note_shows_once_then_block_is_stable(catalog, profile):
    execute_education_tool("show_country_matches", {}, profile, catalog)
    apply_updates(profile, {"english_score": 5.0})
    changed = execute_education_tool("show_country_matches", {}, profile, catalog).block
    again = execute_education_tool("show_country_matches", {}, profile, catalog).block
    assert changed.changed_because
    assert again.changed_because is None
    assert again.data == changed.data


def test_scoring_is_deterministic_and_stably_ordered(catalog, profile):
    runs = [score_countries(profile, catalog) for _ in range(5)]
    assert all(r == runs[0] for r in runs)
    scores = [i["score"] for i in runs[0]]
    assert scores == sorted(scores, reverse=True)

    # ties break by id, not by input order
    tie = Catalog(site_id="t", countries=list(reversed(make_catalog().countries)))
    tied = [i["id"] for i in score_countries({"budget": 10**6}, tie)]  # everyone scores 100
    assert tied == sorted(tied)


def test_comparison_row_order_is_fixed(catalog, profile):
    a = execute_education_tool("compare_countries", {"countries": ["UK", "Australia"]}, profile, catalog).block
    b = execute_education_tool("compare_countries", {"countries": ["Australia", "UK"]}, new_profile(), catalog).block
    assert [r["label"] for r in a.data["rows"]] == [r["label"] for r in b.data["rows"]]


# ---- no invented data ----

def test_no_scores_when_profile_has_nothing_to_evaluate(catalog):
    out = execute_education_tool("show_country_matches", {}, new_profile(), catalog)
    assert out.block is None
    assert "missing" in out.message


def test_empty_catalog_never_produces_a_card():
    empty = Catalog(site_id="nobody")
    p = new_profile()
    apply_updates(p, {"budget": 30000})
    for tool, args in [("show_choice", {"kind": "countries"}), ("show_country_matches", {}),
                       ("show_country_facts", {"country": "uk"}), ("show_budget_slider", {}),
                       ("compare_countries", {"countries": ["uk", "au"]}), ("check_eligibility", {"country": "uk"})]:
        assert execute_education_tool(tool, args, p, empty).block is None, tool


def test_facts_only_show_what_the_catalog_has(catalog, profile):
    block = execute_education_tool("show_country_facts", {"country": "ca"}, profile, catalog).block
    labels = [r["label"] for r in block.data["rows"]]
    assert "Work rights" not in labels and "Post-study visa" not in labels  # Canada has none on file
    assert "Tuition / year" in labels


def test_eligibility_uses_only_known_requirements(catalog):
    p = new_profile()
    apply_updates(p, {"english_score": 6.0})
    block = execute_education_tool("check_eligibility", {"country": "uk"}, p, catalog).block
    assert [c["label"] for c in block.data["checks"]] == ["English score"]  # no academic score given -> not guessed
    assert block.data["checks"][0]["ok"] is False


# ---- schema validation ----

def test_invalid_blocks_are_rejected():
    with pytest.raises(BlockValidationError):
        build_block("nope", {}, fallback_text="x")
    with pytest.raises(BlockValidationError):
        build_block("range_slider", {"field": "budget", "min": 10, "max": 5, "step": 1, "value": 7, "unit": "$"},
                    fallback_text="x")
    with pytest.raises(BlockValidationError):
        build_block("comparison_table", {"columns": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                                         "rows": [{"label": "x", "values": ["only one"]}]}, fallback_text="x")
    with pytest.raises(BlockValidationError):
        build_block("match_cards", {"items": [{"id": "a", "label": "A", "score": 140}]}, fallback_text="x")


def test_identical_content_gets_identical_block_id():
    data = {"chips": [{"id": "a", "label": "A"}]}
    assert build_block("quick_chips", data, fallback_text="x").block_id == build_block("quick_chips", data, fallback_text="x").block_id


# ---- profile reducer (taps) ----

def test_tap_actions_update_profile_deterministically():
    p = new_profile()
    assert apply_block_action(p, {"actionId": "select", "values": {"field": "countries", "selected": ["uk", "au"]}}) == ["countries"]
    assert p["countries"] == ["au", "uk"]
    assert apply_block_action(p, {"actionId": "set_value", "values": {"field": "budget", "value": 25000}}) == ["budget"]
    assert apply_block_action(p, {"actionId": "select", "values": {"field": "study_level", "selected": ["master"]}}) == ["study_level"]
    assert apply_block_action(p, {"actionId": "submit", "values": {"name": "Ram", "email": "r@x.com", "phone": "98"}}) == ["contact"]
    assert p["contact"]["email"] == "r@x.com"


def test_profile_rejects_unknown_fields_and_bad_values():
    p = new_profile()
    assert apply_block_action(p, {"actionId": "set_value", "values": {"field": "is_admin", "value": 1}}) == []
    assert apply_block_action(p, {"actionId": "set_value", "values": {"field": "budget", "value": "lots"}}) == []
    assert apply_updates(p, {"password": "x", "budget": "30000"}) == ["budget"]
    assert p["budget"] == 30000 and "password" not in p
    assert apply_block_action(p, None) == []
