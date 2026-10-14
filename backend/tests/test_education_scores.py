"""A score is only meaningful with its unit. The AI saved "3.64 gpa" as `academic_score = 3.64`, the field the catalog compares
with a PERCENTAGE minimum, so the next eligibility check told the student they did not qualify; and "7 is my english score"
was never saved because the AI asked "check eligibility" before "save profile". Scores are now read from the student's own
words in code, the unit is kept (percentage, or GPA with its scale), a GPA is converted by one explicit estimate rule, and an
English score is only compared with the IELTS minimum when it is an IELTS score."""
import pytest

from app.services.education_catalog import CountryRecord, check_eligibility
from app.services.education_profile import apply_updates, new_profile
from app.services.education_scores import academic_percent, extract_scores, gpa_to_percent, ielts_comparable
from tests.test_education_agent import _catalog, _chunk, make_agent, run  # noqa: F401 (_catalog is autouse)


# --- reading scores from what the student wrote ---------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("7 is my english test socre", {"english_score": 7}),                       # the real message, typo included
    ("my ielts is 6.5", {"english_test": "IELTS", "english_score": 6.5}),
    ("I got 6.5 in IELTS", {"english_test": "IELTS", "english_score": 6.5}),
    ("i scored 90 in toefl", {"english_test": "TOEFL", "english_score": 90}),
    ("my PTE score is 65", {"english_test": "PTE", "english_score": 65}),
    ("3.64 gpa", {"academic_gpa": 3.64, "academic_gpa_scale": 4}),               # the real message
    ("my gpa is 8.5", {"academic_gpa": 8.5, "academic_gpa_scale": 10}),
    ("my cgpa is 3.2/4", {"academic_gpa": 3.2, "academic_gpa_scale": 4}),
    ("gpa 7.8 out of 10", {"academic_gpa": 7.8, "academic_gpa_scale": 10}),
    ("my percentage is 72", {"academic_score": 72}),
    ("I scored 65% in my bachelor", {"academic_score": 65}),
    ("my ielts is 6.5 and my gpa is 3.5",
     {"english_test": "IELTS", "english_score": 6.5, "academic_gpa": 3.5, "academic_gpa_scale": 4}),
])
def test_scores_are_read_with_their_unit(text, expected):
    assert extract_scores(text) == expected


@pytest.mark.parametrize("text", [
    "hello",
    "what ielts do I need for the UK?",
    "UK requires ielts 6.5",                  # a requirement, not the student's score
    "which countries need 65% marks?",
    "minimum gpa for canada",
    "my budget is 20%",
    "my english is good",
    "7 is my lucky number",
    "my ielts is 15",                          # not a possible IELTS score
    "my gpa is 12",                            # more than any scale
    "I want to start in 2026",
])
def test_nothing_is_read_from_questions_requirements_or_impossible_values(text):
    assert extract_scores(text) == {}


# --- the profile keeps the unit -------------------------------------------------------------------------------------

def test_a_gpa_the_ai_saved_as_an_academic_score_is_kept_as_a_gpa_not_a_percentage():
    profile = new_profile()
    assert apply_updates(profile, {"academic_score": 3.64}) == ["academic_gpa", "academic_gpa_scale"]
    assert "academic_score" not in profile and profile["academic_gpa"] == 3.64 and profile["academic_gpa_scale"] == 4


def test_a_ten_point_cgpa_is_kept_with_its_scale():
    profile = new_profile()
    apply_updates(profile, {"academic_score": 8.5})
    assert profile["academic_gpa"] == 8.5 and profile["academic_gpa_scale"] == 10 and "academic_score" not in profile


def test_a_real_percentage_is_saved_and_an_impossible_one_is_not():
    profile = new_profile()
    apply_updates(profile, {"academic_score": 72})
    assert profile["academic_score"] == 72
    p2 = new_profile()
    assert apply_updates(p2, {"academic_score": 150}) == [] and "academic_score" not in p2


def test_a_gpa_above_its_scale_is_rejected():
    profile = new_profile()
    assert apply_updates(profile, {"academic_gpa": 5, "academic_gpa_scale": 4}) == []


# --- the one conversion rule ----------------------------------------------------------------------------------------

def test_gpa_to_percent_is_a_plain_proportion():
    assert gpa_to_percent(3.64, 4) == pytest.approx(91.0)
    assert gpa_to_percent(8.5, 10) == pytest.approx(85.0)


def test_academic_percent_prefers_a_real_percentage_and_marks_a_converted_gpa():
    assert academic_percent({"academic_score": 72, "academic_gpa": 3.0, "academic_gpa_scale": 4}) == (72, None)
    pct, source = academic_percent({"academic_gpa": 3.64, "academic_gpa_scale": 4})
    assert pct == pytest.approx(91.0) and source == (3.64, 4)
    assert academic_percent({}) == (None, None)


def test_an_old_profile_that_stored_a_gpa_as_academic_score_is_not_read_as_a_percentage():
    assert academic_percent({"academic_score": 3.64}) == (None, None)


def test_only_an_ielts_score_is_compared_with_the_ielts_minimum():
    assert ielts_comparable({"english_score": 7}) == 7                                  # test not named: as before
    assert ielts_comparable({"english_test": "IELTS", "english_score": 6.5}) == 6.5
    assert ielts_comparable({"english_test": "TOEFL", "english_score": 90}) is None


# --- eligibility uses the unit ---------------------------------------------------------------------------------------

USA = CountryRecord(id="us", label="U.S.A.", ielts_min=6.5, academic_min_percent=65)


def test_eligibility_checks_a_converted_gpa_and_says_it_is_an_estimate():
    result = check_eligibility({"english_score": 7, "academic_gpa": 3.64, "academic_gpa_scale": 4}, USA)
    academic = next(c for c in result["checks"] if c["label"] == "Academic score")
    assert academic["ok"] is True
    assert "estimated" in academic["detail"] and "3.64" in academic["detail"] and "91%" in academic["detail"]
    assert result["verdict"] == "You meet the requirements we can check"


def test_eligibility_does_not_fail_a_student_because_a_gpa_was_read_as_a_percentage():
    result = check_eligibility({"english_score": 7, "academic_score": 3.64}, USA)     # legacy bad value
    assert [c["label"] for c in result["checks"]] == ["English score"]                 # academic is skipped, not failed


def test_eligibility_skips_the_english_check_for_a_non_ielts_test():
    assert check_eligibility({"english_test": "TOEFL", "english_score": 90}, USA) is None
    result = check_eligibility({"english_test": "TOEFL", "english_score": 90, "academic_score": 70}, USA)
    assert [c["label"] for c in result["checks"]] == ["Academic score"]                # 90 is never compared with 6.5


# --- the real conversation -------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_scores_in_the_real_conversation_are_saved_even_if_the_ai_never_calls_update_profile():
    agent = make_agent([[_chunk("Thanks.")], [_chunk("Thanks.")]])
    await run(agent, "7 is my english test socre")
    await run(agent, "3.64 gpa")
    profile = await agent.memory.load_profile(None, "s1")
    assert profile["english_score"] == 7
    assert profile["academic_gpa"] == 3.64 and profile["academic_gpa_scale"] == 4
    assert "academic_score" not in profile


@pytest.mark.asyncio
async def test_a_question_does_not_overwrite_what_the_student_said():
    agent = make_agent([[_chunk("Thanks.")], [_chunk("It depends.")]])
    await run(agent, "my ielts is 6.5")
    await run(agent, "the uk needs ielts 7 apparently")
    assert (await agent.memory.load_profile(None, "s1"))["english_score"] == 6.5
