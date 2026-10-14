"""Grounding check: a sentence the LLM writes freely is kept only if something we hold backs any risky claim in it. Built
from two real failures found against the live LLM: Admizz's "high visa approval rate" became "Canada has a high visa
approval rate", and replies offered to "explore universities or programs" that we have no data for."""
import copy
import logging

import pytest

from app.services import education_agent
from app.services.education_catalog import Catalog, CountryRecord, register_catalog
from app.services.education_grounding import CLAIMS, build_support, catalog_sources, check_answer
from app.services.education_leadins import KB_MISS
from app.services.education_catalog_models import University
from app.services.education_profile import apply_updates, new_profile
from tests.test_education_agent import _chunk, blocks_of, make_agent, run
from tests.test_education_consistency import make_catalog

BRAND = "Admizz Education"
FAQ = {"source_title": "FAQ", "content": "Q: Why should I choose Admizz Education over other consultancies? "
       "A: Admizz Education is trusted by students worldwide, has a high visa approval rate, and offers personalized support."}
COUNTRY_PAGE = {"source_title": "Country", "content": "Explore World-Class Education in a Dynamic Global Hub Capital Language Dialing Code "
                "Currency Population Universities Intl. Students Tuition fee Student Visa Approval Rate with Expert Guidance In Scholarships Awarded"}
SCHOLARSHIP = {"source_title": "Services", "content": "Admizz offers scholarship guidance and test preparation courses for students."}


@pytest.fixture
def catalog():
    return make_catalog()


def check(answer, catalog, chunks=(), question="", shown=(), **profile):
    p = new_profile()
    apply_updates(p, profile)
    docs = build_support(list(chunks), catalog, p, list(shown), question)
    return check_answer(answer, docs, catalog, BRAND)


# ---- the two real failures ----

def test_admizzs_own_claim_is_not_passed_off_as_canadas(catalog):
    r = check("Canada has a high visa approval rate with expert guidance.", catalog, [FAQ, COUNTRY_PAGE])
    assert r.empty and r.reasons == ["visa_outcome"]


def test_the_same_claim_about_admizz_or_we_is_kept(catalog):
    for sentence in ("Admizz has a high visa approval rate.", "We have a high visa approval rate.", "Our visa approval rate is high."):
        assert check(sentence, catalog, [FAQ]).text == sentence


def test_a_claim_about_a_country_is_kept_when_a_source_says_it_about_that_country(catalog):
    page = {"content": "Canada offers a strong visa approval rate for students.\nStudy options are wide."}
    assert check("Canada has a strong visa approval rate.", catalog, [page]).text == "Canada has a strong visa approval rate."
    assert check("Australia has a strong visa approval rate.", catalog, [page]).empty


def test_offers_of_universities_and_programs_are_dropped_while_we_have_none(catalog):
    r = check("Thank you! Would you like to explore universities or programs in Canada?", catalog)
    assert r.text == "Thank you!" and r.reasons == ["undeliverable_offer"]
    assert check("Would you like to see specific courses?", catalog).empty


def test_those_offers_are_allowed_once_the_catalog_has_university_data(catalog):
    with_data = catalog.model_copy(update={"universities": [University(id="u1", name="U", country_id="uk")]})
    assert check("Would you like to explore universities in the U.K.?", with_data).text == "Would you like to explore universities in the U.K.?"


def test_a_plain_statement_about_courses_is_not_an_offer(catalog):
    assert check("Admizz Education offers test preparation courses.", catalog, [SCHOLARSHIP]).kept == 1


# ---- numbers ----

def test_a_number_nobody_gave_is_dropped(catalog):
    assert check("Tuition in the U.K. is about $20,000 a year.", catalog).reasons == ["number"]


def test_numbers_from_the_catalog_are_backed_with_or_without_commas(catalog):
    assert check("The U.K. costs between $15,000 and $25,000 a year in tuition.", catalog).kept == 1
    assert check("Tuition in the U.K. is 15000 to 25000.", catalog).kept == 1


def test_all_numbers_in_a_sentence_must_be_backed(catalog):
    assert check("The U.K. tuition is 15000 to 99999.", catalog).empty


def test_the_students_own_numbers_and_profile_may_be_repeated(catalog):
    assert check("Great, 6.5 is a solid score.", catalog, question="my IELTS is 6.5").kept == 1
    assert check("Your budget of $25,000 a year is noted.", catalog, budget=25000).kept == 1
    assert check("Your budget of $30,000 a year is noted.", catalog, budget=25000).empty


def test_a_requirement_is_backed_for_its_own_country_only(catalog):
    assert check("The U.K. needs an IELTS of 6.5.", catalog).kept == 1
    assert check("Australia needs an IELTS of 6.5.", catalog).empty          # Australia's minimum in the catalog is 6


def test_a_card_shown_this_turn_backs_what_it_says(catalog):
    assert check("It says the U.K. is a Strong fit.", catalog, shown=["Fit with what you told us: U.K. (Strong fit)."]).kept == 1


# ---- cost comparisons, scholarships, work rights ----

def test_a_cost_comparison_between_countries_needs_a_source_naming_both(catalog):
    answer = "Canada generally offers lower tuition fees compared to the U.K."
    assert check(answer, catalog).reasons == ["cost_comparison"]
    page = {"content": "Canada has lower tuition fees than the U.K. for most programs."}
    assert check(answer, catalog, [page]).kept == 1


def test_scholarship_claims_need_backing(catalog):
    assert check("We provide guidance on scholarships.", catalog).reasons == ["scholarship"]
    assert check("We provide guidance on scholarships.", catalog, [SCHOLARSHIP]).kept == 1
    assert check("We provide guidance on scholarships.", catalog, [COUNTRY_PAGE]).empty     # a page heading is not a claim about us


def test_work_rights_are_backed_by_the_catalog(catalog):
    assert check("The U.K. offers post-study work for 2 years.", catalog).kept == 1
    assert check("The U.K. offers post-study work for 5 years.", catalog).empty
    assert check("Canada offers post-study work for 2 years.", catalog).empty


def test_claim_and_country_must_sit_close_together_in_the_source(catalog):
    far = {"content": "Canada is a popular choice.\nStudents love it.\nIt is lively.\nVisa approval rate is high for applicants."}
    near = {"content": "Canada is a popular choice.\nVisa approval rate is high for Canada applicants."}
    sentence = "Canada has a high visa approval rate."
    assert check(sentence, catalog, [far]).empty and check(sentence, catalog, [near]).kept == 1


# ---- absolute claims and honest disclaimers ----

def test_a_disclaimer_about_guarantees_is_honest_and_passes(catalog):
    sentence = "While we offer visa guidance, we cannot guarantee visa approval."
    assert check(sentence, catalog).text == sentence


def test_a_guarantee_is_not_backed_by_a_high_approval_rate(catalog):
    assert check("Admizz guarantees visa approval.", catalog, [FAQ]).empty
    assert check("Admizz guarantees visa approval.", catalog, [{"content": "Admizz guarantees visa approval for all."}]).kept == 1


# ---- everything else passes untouched ----

@pytest.mark.parametrize("sentence", [
    "Hello! How can I help you today?", "What would you like to do next?", "Thank you for sharing your IELTS score.",
    "Could you please share your field of study?", "I'm always happy to help.", "Let me know if you have any other questions.",
])
def test_conversation_is_never_touched(catalog, sentence):
    r = check(sentence, catalog)
    assert r.text == sentence and r.dropped == 0


def test_supported_and_unsupported_sentences_are_separated_in_order(catalog):
    answer = "Admizz has a high visa approval rate. Canada has a high visa approval rate. What would you like to do next?"
    r = check(answer, catalog, [FAQ])
    assert r.text == "Admizz has a high visa approval rate. What would you like to do next?"
    assert (r.kept, r.dropped) == (2, 1)


def test_abbreviations_in_country_names_do_not_break_sentences(catalog):
    r = check("Welcome to the U.K. guide. The U.K. needs an IELTS of 6.5.", catalog)
    assert r.kept >= 1 and "6.5" in r.text


def test_reasons_name_kinds_of_claim_only_never_the_text(catalog):
    r = check("Canada has the cheapest tuition. We guarantee 100% visa approval. Zorblax has 500 scholarships.", catalog)
    assert set(r.reasons) <= set(CLAIMS) | {"number", "undeliverable_offer"}
    assert not any("Zorblax" in x for x in r.reasons)


def test_an_empty_answer_is_empty(catalog):
    assert check("", catalog).empty


def test_the_check_is_deterministic_and_changes_nothing_it_is_given(catalog):
    docs = build_support([FAQ], catalog, new_profile(), [], "q")
    before = copy.deepcopy(docs)
    a = check_answer("Canada has a high visa approval rate. Hi!", docs, catalog, BRAND)
    b = check_answer("Canada has a high visa approval rate. Hi!", docs, catalog, BRAND)
    assert a == b and docs == before


def test_the_catalog_is_turned_into_one_statement_per_country(catalog):
    docs = catalog_sources(catalog)
    assert len(docs) == len(catalog.countries) and all(len(d) == 1 for d in docs)
    assert "tuition 15000 to 25000" in docs[0][0] and "U.K." in docs[0][0]


# ---- the agent ----

@pytest.fixture(autouse=True)
def _agent_catalog():
    from app.services import education_kb_blocks
    education_kb_blocks._llm_shape_cache.clear()
    education_kb_blocks._shared_cache.clear()
    cat = make_catalog()
    cat.site_id = "edu-agent-test"
    register_catalog(cat)


OPEN = "I am curious about the visa side"          # no rule, not a question: the LLM answers in plain text


def tokens(events):
    return [e["data"] for e in events if e["type"] == "token"]


@pytest.mark.asyncio
async def test_a_misattributed_claim_is_dropped_from_the_reply_the_student_sees(caplog):
    caplog.set_level(logging.INFO, logger="zunkiree.education_agent")
    agent = make_agent([[_chunk("Canada has a high visa approval rate with expert guidance. What would you like to do next?")]],
                       chunks=[FAQ, COUNTRY_PAGE])
    events = await run(agent, OPEN)
    assert "".join(tokens(events)) == "What would you like to do next?" == events[-1]["answer"]
    [_, assistant] = await agent.memory.list_messages(None, "s1")
    assert assistant["content"] == "What would you like to do next?"                        # and that is what is saved
    line = next(r.getMessage() for r in caplog.records if "grounding dropped" in r.getMessage())
    assert line == "[EDU] grounding dropped=1 kept=1 kinds=['visa_outcome']"                 # kinds only, never the text


@pytest.mark.asyncio
async def test_a_supported_claim_is_kept():
    agent = make_agent([[_chunk("Admizz has a high visa approval rate.")]], chunks=[FAQ])
    assert "".join(tokens(await run(agent, OPEN))) == "Admizz has a high visa approval rate."


@pytest.mark.asyncio
async def test_when_nothing_can_be_backed_the_student_gets_the_honest_answer_and_the_counselor_button():
    agent = make_agent([[_chunk("Canada has a high visa approval rate. Tuition there is $9,999 a year.")]], chunks=[FAQ])
    events = await run(agent, OPEN)
    assert "".join(tokens(events)) == KB_MISS
    assert [b["type"] for b in blocks_of(events)] == ["quick_chips"]
    assert blocks_of(events)[0]["data"]["chips"][0]["id"] == "lead"


@pytest.mark.asyncio
async def test_without_compositions_the_honest_answer_has_no_button(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_compositions", False)
    agent = make_agent([[_chunk("Canada has a high visa approval rate.")]], chunks=[FAQ])
    events = await run(agent, OPEN)
    assert "".join(tokens(events)) == KB_MISS and blocks_of(events) == []


@pytest.mark.asyncio
async def test_an_offer_of_universities_is_removed_from_a_friendly_reply():
    agent = make_agent([[_chunk("Thank you for sharing! Would you like to explore universities or programs?")]])
    assert "".join(tokens(await run(agent, "My IELTS is 6.5 and my score was 70 percent"))) == "Thank you for sharing!"


@pytest.mark.asyncio
async def test_the_reply_is_sent_once_checked_not_word_by_word():
    agent = make_agent([[_chunk("Happy "), _chunk("to "), _chunk("help.")]])
    events = await run(agent, "just saying hello to you")
    assert tokens(events) == ["Happy to help."]


@pytest.mark.asyncio
async def test_with_the_switch_off_the_reply_streams_unchecked(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_grounding_check", False)
    agent = make_agent([[_chunk("Canada has a high "), _chunk("visa approval rate.")]], chunks=[FAQ])
    assert tokens(await run(agent, OPEN)) == ["Canada has a high ", "visa approval rate."]


@pytest.mark.asyncio
async def test_a_message_in_another_language_is_not_checked_because_the_check_reads_english_only():
    agent = make_agent([[_chunk("Canada ma visa approval rate high cha.")]], chunks=[FAQ])
    assert "".join(tokens(await run(agent, "malai visa ko barema kehi batau"))) == "Canada ma visa approval rate high cha."


@pytest.mark.asyncio
async def test_the_next_turn_sees_the_checked_reply_not_the_dropped_sentence():
    agent = make_agent([[_chunk("Canada has a high visa approval rate. Anything else?")], [_chunk("Sure.")]], chunks=[FAQ])
    await run(agent, OPEN)
    await run(agent, "and one more thing")
    history = [m["content"] for m in agent.client.calls[1]["messages"] if m["role"] == "assistant"]
    assert history == ["Anything else?"]


@pytest.mark.asyncio
async def test_a_tool_calling_reply_with_no_text_is_untouched():
    from tests.test_education_agent import _tool_chunk
    agent = make_agent([[_tool_chunk("update_profile", {"budget": 25000})], [_chunk("Noted, thanks!")]])
    assert "".join(tokens(await run(agent, "I can spend 25000"))) == "Noted, thanks!"


@pytest.mark.asyncio
async def test_a_templated_card_reply_is_not_run_through_the_check():
    agent = make_agent([])
    p = new_profile()
    apply_updates(p, dict(budget=40000, english_score=6.5, academic_score=70))
    agent.memory.profiles[(None, "s1")] = p
    events = await run(agent, "Which countries fit my profile?")
    assert agent.client.calls == [] and "lines up strongly" in "".join(tokens(events))


def test_the_check_is_on_by_default():
    from app.config import Settings
    assert Settings.model_fields["education_grounding_check"].default is True
