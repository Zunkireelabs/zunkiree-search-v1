"""Fit tiers replace the percentage score. A tier says how the student's own details line up with the catalog; it is not a
chance of admission or of a visa. The rule has no weights: any failed check -> needs review; otherwise two or more checks
that all pass -> strong; at most one partial -> good; more -> possible."""
import copy

import pytest

from app.schemas.ui_blocks import UI_TYPES, BlockValidationError, build_block, is_current, upgrade_stored_block
from app.services.education_actions import validate_block_action
from app.services.education_catalog import TIER_LABELS, TIER_ORDER, Catalog, CountryRecord, _tier, fit_countries
from app.services.education_profile import apply_updates, new_profile
from app.services.education_tools import execute_education_tool


def country(**kw) -> CountryRecord:
    base = dict(id="xx", label="Xland", tuition_min=10000, tuition_max=20000, living_min=5000, living_max=10000,
                ielts_min=6.5, academic_min_percent=60, intakes=["September", "January"])
    return CountryRecord(**{**base, **kw})


def fit(profile_fields: dict, *countries: CountryRecord) -> list[dict]:
    p = new_profile()
    apply_updates(p, profile_fields)
    return fit_countries(p, Catalog(site_id="t", currency="USD", countries=list(countries or [country()])))


def statuses(item) -> list[str]:
    return [r["status"] for r in item["reasons"]]


# yearly range for the default country is 15,000 - 30,000
ALL_PASS = {"budget": 40000, "english_score": 7, "academic_score": 70}


# ---- the tier rule itself (every combination of counts) ----

@pytest.mark.parametrize("passed,partial,failed,tier", [
    (3, 0, 0, "strong"), (2, 0, 0, "strong"), (4, 0, 0, "strong"),
    (1, 0, 0, "good"), (0, 0, 0, "good"),
    (2, 1, 0, "good"), (1, 1, 0, "good"), (0, 1, 0, "good"),
    (1, 2, 0, "possible"), (0, 2, 0, "possible"), (3, 2, 0, "possible"),
    (3, 0, 1, "needs_review"), (0, 0, 1, "needs_review"), (2, 2, 1, "needs_review"), (0, 3, 2, "needs_review"),
])
def test_the_tier_rule(passed, partial, failed, tier):
    assert _tier(passed, partial, failed) == tier


def test_tier_labels_cover_every_tier_and_are_plain_words():
    assert set(TIER_LABELS) == set(TIER_ORDER)
    assert list(TIER_LABELS.values()) == ["Strong fit", "Good fit", "Possible fit", "Needs review"]


# ---- how each check comes out ----

def test_everything_lines_up_is_a_strong_fit():
    [item] = fit(ALL_PASS)
    assert item["tier"] == "strong" and item["tier_label"] == "Strong fit"
    assert statuses(item) == ["pass", "pass", "pass"]


def test_budget_covering_only_the_minimum_is_partial():
    [item] = fit({**ALL_PASS, "budget": 20000})
    assert statuses(item)[0] == "partial" and item["tier"] == "good"
    assert "Within your budget for most options" in item["reasons"][0]["text"]


def test_budget_below_the_minimum_fails_and_needs_review():
    [item] = fit({**ALL_PASS, "budget": 9000})
    assert statuses(item)[0] == "fail" and item["tier"] == "needs_review"
    assert item["reasons"][0]["text"].startswith("Above your budget (from $15,000/yr)")


@pytest.mark.parametrize("field,value,reason_start", [
    ("english_score", 6.0, "English score is below the 6.5 minimum"),
    ("academic_score", 50, "Academic score is below the 60% minimum"),
])
def test_a_score_below_the_minimum_fails(field, value, reason_start):
    [item] = fit({**ALL_PASS, field: value})
    assert item["tier"] == "needs_review" and any(r["status"] == "fail" and r["text"] == reason_start for r in item["reasons"])


def test_a_score_exactly_at_the_minimum_passes():
    [item] = fit({"english_score": 6.5, "academic_score": 60})
    assert statuses(item) == ["pass", "pass"] and item["tier"] == "strong"


def test_one_failed_check_beats_any_number_of_passes():
    [item] = fit({**ALL_PASS, "english_score": 4})
    assert statuses(item).count("pass") == 2 and item["tier"] == "needs_review"


def test_a_single_passing_check_is_good_not_strong():
    [item] = fit({"budget": 40000})
    assert item["tier"] == "good"


def test_two_partials_make_a_possible_fit():
    [item] = fit({"budget": 20000, "intake": "March"})
    assert statuses(item) == ["partial", "partial"] and item["tier"] == "possible"


def test_intake_pass_is_case_insensitive_and_a_miss_lists_what_is_offered():
    [hit] = fit({**ALL_PASS, "intake": "september"})
    hit_reason = next(r for r in hit["reasons"] if "intake" in r["text"])
    assert hit_reason["status"] == "pass" and hit["tier"] == "strong"
    [miss] = fit({**ALL_PASS, "intake": "March"})
    miss_reason = next(r for r in miss["reasons"] if "intake" in r["text"])
    assert miss_reason["status"] == "partial" and "September, January" in miss_reason["text"]


def test_a_country_with_no_listed_intakes_is_not_judged_on_intake():
    [item] = fit({**ALL_PASS, "intake": "March"}, country(intakes=[]))
    assert not any("intake" in r["text"] for r in item["reasons"])


def test_the_post_study_visa_is_information_and_never_changes_the_tier():
    plain = fit(ALL_PASS)[0]
    with_visa = fit(ALL_PASS, country(post_study_visa="2 years"))[0]
    assert with_visa["tier"] == plain["tier"]
    assert with_visa["reasons"][-1] == {"status": "info", "text": "Post-study work: 2 years"}


# ---- missing data is never guessed ----

def test_nothing_to_evaluate_leaves_the_country_out():
    assert fit({}) == []
    assert fit({"intake": "September"}) == []          # an intake alone says nothing


def test_a_check_the_catalog_cannot_run_is_skipped_not_failed():
    [item] = fit({"budget": 40000, "english_score": 4}, country(ielts_min=None))
    assert item["tier"] == "good" and statuses(item) == ["pass"]


def test_each_country_is_judged_on_the_data_it_has():
    items = fit({"budget": 40000, "academic_score": 50}, country(id="a"), country(id="b", academic_min_percent=None))
    by_id = {i["id"]: i for i in items}
    assert by_id["a"]["tier"] == "needs_review" and by_id["b"]["tier"] == "good"


# ---- ordering and determinism ----

def test_ordered_by_tier_then_more_passes_then_id():
    strong2 = country(id="d")                                            # budget + english + academic pass
    strong_fewer = country(id="b", academic_min_percent=None)            # budget + english pass
    good = country(id="c", tuition_max=60000)                            # budget partial
    review = country(id="a", ielts_min=9)                                # english fails
    items = fit(ALL_PASS, review, good, strong_fewer, strong2)
    assert [i["id"] for i in items] == ["d", "b", "c", "a"]
    assert [i["tier"] for i in items] == ["strong", "strong", "good", "needs_review"]


def test_equal_fits_are_ordered_by_id_not_input_order():
    items = fit(ALL_PASS, country(id="z"), country(id="m"), country(id="a"))
    assert [i["id"] for i in items] == ["a", "m", "z"]


def test_same_input_same_output():
    runs = [fit({**ALL_PASS, "intake": "March"}, country(id="a"), country(id="b", ielts_min=9)) for _ in range(5)]
    assert all(r == runs[0] for r in runs)


# ---- no percentages, no invented superlatives ----

def test_items_carry_no_numeric_score():
    for item in fit(ALL_PASS):
        assert set(item) == {"id", "label", "icon", "tier", "tier_label", "reasons"}


def test_the_block_never_claims_a_best_match_or_a_percentage_headline():
    block = execute_education_tool("show_country_matches", {}, _profile(), _catalog()).block
    for item in block.data["items"]:
        assert "score" not in item and "best" not in item["tier_label"].lower()
    assert "%" not in block.fallback_text and "best" not in block.fallback_text.lower()


def test_the_lead_in_instruction_forbids_percentages_best_and_admission_claims():
    msg = execute_education_tool("show_country_matches", {}, _profile(), _catalog()).message
    assert "never call anything 'best'" in msg and "never give percentages" in msg and "chance of admission" in msg


def _catalog() -> Catalog:
    return Catalog(site_id="t", currency="USD", countries=[country(id="uk", label="U.K."), country(id="au", label="Australia", ielts_min=9)])


def _profile() -> dict:
    p = new_profile()
    apply_updates(p, ALL_PASS)
    return p


# ---- schema ----

GOOD_ITEM = {"id": "uk", "label": "U.K.", "tier": "good", "tier_label": "Good fit", "reasons": [{"status": "pass", "text": "ok"}]}


def test_a_valid_v2_match_block_builds_at_version_2():
    block = build_block("match_cards", {"items": [GOOD_ITEM]}, fallback_text="x")
    assert block.schema_version == 2


@pytest.mark.parametrize("bad", [
    {**GOOD_ITEM, "tier": "excellent"},
    {**GOOD_ITEM, "score": 90},                                          # the old percentage may not slip through
    {k: v for k, v in GOOD_ITEM.items() if k != "tier"},
    {**GOOD_ITEM, "reasons": [{"status": "great", "text": "x"}]},
    {**GOOD_ITEM, "reasons": ["Fits your budget"]},                      # the old plain-string reasons
])
def test_malformed_or_v1_shaped_items_are_rejected(bad):
    with pytest.raises(BlockValidationError):
        build_block("match_cards", {"items": [bad]}, fallback_text="x")


def test_eligibility_no_longer_accepts_a_percentage():
    ok = {"verdict": "v", "checks": [{"label": "a", "ok": True, "detail": "d"}]}
    assert build_block("eligibility_meter", ok, fallback_text="x").schema_version == 2
    with pytest.raises(BlockValidationError):
        build_block("eligibility_meter", {**ok, "score": 80}, fallback_text="x")


def test_eligibility_output_has_no_score_and_no_percent_in_its_text():
    p = new_profile()
    apply_updates(p, {"english_score": 7, "academic_score": 70})
    cat = Catalog(site_id="t", currency="USD", countries=[country(id="uk", label="U.K.")])
    block = execute_education_tool("check_eligibility", {"country": "uk"}, p, cat).block
    assert "score" not in block.data and "%" not in block.fallback_text


# ---- versioning: only these two types moved to v2 ----

def test_only_match_cards_and_eligibility_meter_are_at_version_2():
    assert {t for t, s in UI_TYPES.items() if s.version == 2} == {"match_cards", "eligibility_meter"}


def test_there_is_deliberately_no_upgrader_from_a_percentage_to_a_tier():
    assert UI_TYPES["match_cards"].upgraders == {} and UI_TYPES["eligibility_meter"].upgraders == {}


V1_MATCH = {"block_id": "match_cards-old", "type": "match_cards", "schema_version": 1, "title": "Countries that match your profile",
            "data": {"items": [{"id": "uk", "label": "U.K.", "score": 90, "reasons": ["Fits your $40,000 budget"]}]},
            "actions": [], "fallback_text": "Best matches: U.K. 90%."}


def test_a_stored_v1_match_block_is_never_pretended_to_be_current():
    assert not is_current(V1_MATCH) and upgrade_stored_block(V1_MATCH) is V1_MATCH


def test_a_cached_v1_match_block_is_rebuilt_as_a_tier_block_without_an_updated_note():
    profile, cat = _profile(), _catalog()
    execute_education_tool("show_country_matches", {}, profile, cat)
    key = "recommend_country:all"
    profile["shown"][key]["block"] = copy.deepcopy(V1_MATCH)                 # as persisted before this change
    again = execute_education_tool("show_country_matches", {}, profile, cat).block
    assert again.schema_version == 2 and again.changed_because is None
    assert "tier" in again.data["items"][0]
    assert profile["shown"][key]["block"]["schema_version"] == 2


def test_the_explore_tap_on_a_v2_match_block_is_still_valid():
    block = execute_education_tool("show_country_matches", {}, _profile(), _catalog()).block.model_dump()
    tap = {"blockId": block["block_id"], "blockType": "match_cards", "actionId": "explore", "values": {"country": "uk"}}
    assert validate_block_action(tap, block) is None
    assert validate_block_action({**tap, "values": {"country": "atlantis"}}, block) == "not_an_option"
