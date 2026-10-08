"""A card the LLM chooses (by calling a tool) gets the same treatment as a card the rules chose: companions (profile
summary, next-step buttons), the remembered "what is on screen" state that makes follow-ups work, and a sentence written by
code from the card. Only the FIRST result card of a turn is composed and remembered."""
import logging
from types import SimpleNamespace

import pytest

from app.services import education_agent
from app.services.education_catalog import Catalog, register_catalog
from app.services.education_compositions import normalized_args
from app.services.education_profile import apply_updates, new_profile
from tests.test_education_agent import _chunk, _tool_chunk, blocks_of, make_agent, run
from tests.test_education_consistency import make_catalog

FULL = dict(budget=40000, english_score=6.5, academic_score=70, intake="September")


@pytest.fixture(autouse=True)
def _agent_catalog():
    from app.services import education_kb_blocks
    education_kb_blocks._llm_shape_cache.clear()
    education_kb_blocks._shared_cache.clear()
    cat = make_catalog()
    cat.site_id = "edu-agent-test"
    register_catalog(cat)


def seed(agent, **fields):
    p = new_profile()
    apply_updates(p, fields)
    agent.memory.profiles[(None, "s1")] = p


def text_of(events):
    return "".join(e["data"] for e in events if e["type"] == "token")


def kinds(events):
    return [b["type"] for b in blocks_of(events)]


def state(agent):
    return agent.memory.profiles[(None, "s1")].get("ui_state")


def second_tool(name, args):
    fn = SimpleNamespace(name=name, arguments=__import__("json").dumps(args))
    return _chunk(tool_calls=[SimpleNamespace(index=1, id="call_2", function=fn)])


# Messages none of the keyword rules recognise, so the LLM (not a rule) decides what to show.
FREE = {
    "show_country_matches": ("Suggest some places where I could do my masters", {}),
    "check_eligibility": ("I'd like to see Australia's entry rules", {"country": "Australia"}),
    "compare_countries": ("Lay out the UK next to Canada for me", {"countries": ["Canada", "U.K."]}),
    "show_country_facts": ("A rundown on Canada, please", {"country": "UK"}),
    "show_cost_calculator": ("Work out a price for Canada", {"country": "Canada"}),
    "show_profile": ("Remind me what you have on file", {}),
}


# ---- the same blocks, state and sentence as a rule-chosen card ----

@pytest.mark.asyncio
async def test_a_card_the_llm_chooses_matches_the_rule_path_block_for_block():
    rule_agent = make_agent([])
    seed(rule_agent, **FULL)
    rule = await run(rule_agent, "Which countries fit my profile?")

    llm_agent = make_agent([[_tool_chunk("show_country_matches", {})]])
    seed(llm_agent, **FULL)
    llm = await run(llm_agent, FREE["show_country_matches"][0])

    assert blocks_of(llm) == blocks_of(rule)                       # identical blocks, ids and all
    assert text_of(llm) == text_of(rule)                           # and the same code-written sentence
    assert len(llm_agent.client.calls) == 1                        # only the tool-choosing call; no second LLM round trip
    assert state(llm_agent)["intent"] == state(rule_agent)["intent"] == "recommend_country"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,expected_kinds,intent,saved_args", [
    ("show_country_matches", ["profile_summary", "match_cards", "quick_chips"], "recommend_country", {}),
    ("check_eligibility", ["eligibility_meter", "quick_chips"], "eligibility", {"country": "au"}),
    ("compare_countries", ["comparison_table", "quick_chips"], "compare", {"countries": ["ca", "uk"]}),
    ("show_country_facts", ["info_card", "quick_chips"], "country_facts", {"country": "uk"}),
    ("show_cost_calculator", ["cost_calculator", "quick_chips"], "cost_calculator", {"country": "ca"}),
    ("show_profile", ["profile_summary", "quick_chips"], "profile", {}),
])
async def test_every_result_tool_gets_its_companions_and_remembered_state(tool, expected_kinds, intent, saved_args):
    question, args = FREE[tool]
    agent = make_agent([[_tool_chunk(tool, args)]])
    seed(agent, **FULL)
    events = await run(agent, question)
    assert kinds(events) == expected_kinds
    assert state(agent)["intent"] == intent and state(agent)["args"] == saved_args     # ids, even though the LLM said names
    assert text_of(events) and len(agent.client.calls) == 1
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_the_whole_composition_is_saved_for_a_reload():
    agent = make_agent([[_tool_chunk("show_country_matches", {})]])
    seed(agent, **FULL)
    await run(agent, FREE["show_country_matches"][0])
    [_, assistant] = await agent.memory.list_messages(None, "s1")
    assert [b["type"] for b in assistant["blocks"]] == ["profile_summary", "match_cards", "quick_chips"]


# ---- what this unlocks: follow-ups and buttons after an LLM-chosen card ----

@pytest.mark.asyncio
async def test_a_budget_follow_up_works_after_an_llm_chosen_recommendation():
    agent = make_agent([[_tool_chunk("show_country_matches", {})]])
    seed(agent, **FULL)
    first = await run(agent, FREE["show_country_matches"][0])
    second = await run(agent, "only under $25k")                    # a follow-up: resolved in code, no LLM
    assert kinds(second) == kinds(first) == ["profile_summary", "match_cards", "quick_chips"]
    assert agent.memory.profiles[(None, "s1")]["budget"] == 25000
    assert "budget" in blocks_of(second)[1]["changed_because"]
    assert len(agent.client.calls) == 1


@pytest.mark.asyncio
async def test_what_about_another_country_works_after_an_llm_chosen_eligibility_check():
    agent = make_agent([[_tool_chunk("check_eligibility", {"country": "Australia"})]])
    seed(agent, **FULL)
    await run(agent, FREE["check_eligibility"][0])
    second = await run(agent, "what about Canada?")
    assert blocks_of(second)[0]["title"] == "Canada eligibility" and state(agent)["args"] == {"country": "ca"}


@pytest.mark.asyncio
async def test_the_buttons_on_an_llm_chosen_card_work_and_pass_tap_validation():
    agent = make_agent([[_tool_chunk("show_country_matches", {})]])
    seed(agent, **FULL)
    chips = next(b for b in blocks_of(await run(agent, FREE["show_country_matches"][0])) if b["type"] == "quick_chips")
    chip = next(c["id"] for c in chips["data"]["chips"] if c["id"].startswith("eligibility:"))
    tap = {"blockId": chips["block_id"], "blockType": "quick_chips", "actionId": chip, "values": {"chip": chip}, "displayText": "x"}
    shown = blocks_of(await run(agent, "x", block_action=tap))
    assert shown[0]["type"] == "eligibility_meter"


# ---- the edges ----

@pytest.mark.asyncio
async def test_an_input_card_chosen_by_the_llm_stays_a_single_card_and_leaves_the_remembered_state_alone():
    agent = make_agent([[_tool_chunk("show_budget_slider", {})], [_chunk("Set it below.")]])
    seed(agent, **FULL)
    agent.memory.profiles[(None, "s1")]["ui_state"] = {"intent": "compare", "args": {"countries": ["uk", "au"]},
                                                      "ui": {"type": "comparison_table", "version": 1}}
    events = await run(agent, "I'd like to set a spending limit")
    assert kinds(events) == ["range_slider"] and state(agent)["intent"] == "compare"
    assert text_of(events) == "Set it below." and len(agent.client.calls) == 2      # the LLM still writes this sentence


@pytest.mark.asyncio
async def test_several_result_cards_in_one_reply_are_shown_plain_and_the_last_is_remembered():
    """Found live: 'Is UK cheaper than Canada?' made the LLM show two cards; buttons landed between them."""
    agent = make_agent([[_tool_chunk("show_country_matches", {}), second_tool("compare_countries", {"countries": ["Canada", "U.K."]})],
                        [_chunk("Both views are above.")]])
    seed(agent, **FULL)
    events = await run(agent, "I'd like both views")
    assert kinds(events) == ["match_cards", "comparison_table"]                      # no profile summary, no buttons in the middle
    assert state(agent)["intent"] == "compare" and state(agent)["args"] == {"countries": ["ca", "uk"]}
    assert text_of(events) == "Both views are above." and len(agent.client.calls) == 2   # the LLM, not a one-card sentence


@pytest.mark.asyncio
async def test_two_countries_facts_in_one_reply_do_not_get_buttons_between_them():
    agent = make_agent([[_tool_chunk("show_country_facts", {"country": "UK"}), second_tool("show_country_facts", {"country": "Canada"})],
                        [_chunk("Here are both.")]])
    seed(agent, **FULL)
    events = await run(agent, "A look at both UK and Canada please")
    assert kinds(events) == ["info_card", "info_card"] and state(agent)["args"] == {"country": "ca"}


@pytest.mark.asyncio
async def test_a_card_plus_an_input_card_in_one_reply_still_composes_the_result_card():
    agent = make_agent([[_tool_chunk("show_country_matches", {}), second_tool("show_budget_slider", {})], [_chunk("Set it below.")]])
    seed(agent, **FULL)
    events = await run(agent, "I'd like matches and a spending limit slider")
    assert kinds(events) == ["profile_summary", "match_cards", "quick_chips", "range_slider"]


@pytest.mark.asyncio
async def test_a_tool_that_builds_nothing_composes_nothing_and_the_llm_carries_on():
    agent = make_agent([[_tool_chunk("check_eligibility", {"country": "Atlantis"})], [_chunk("I don't have that country.")]])
    seed(agent, **FULL)
    events = await run(agent, "Am I good enough for Atlantis")
    assert blocks_of(events) == [] and state(agent) is None
    assert text_of(events) == "I don't have that country." and len(agent.client.calls) == 2


@pytest.mark.asyncio
async def test_profile_facts_saved_in_the_same_response_are_used_by_the_card():
    agent = make_agent([[_tool_chunk("update_profile", {"budget": 25000}), second_tool("show_country_matches", {})]])
    seed(agent, **FULL)
    events = await run(agent, "Let's say 25000 works for me, suggest places for my masters")
    summary = blocks_of(events)[0]
    assert any(r["value"] == "$25,000 / year" for r in summary["data"]["rows"])


@pytest.mark.asyncio
async def test_when_the_llm_already_wrote_text_before_the_tool_call_it_keeps_the_floor():
    agent = make_agent([[_chunk("Let me show you. "), _tool_chunk("show_country_matches", {})], [_chunk("Here they are.")]])
    seed(agent, **FULL)
    events = await run(agent, FREE["show_country_matches"][0])
    assert kinds(events) == ["profile_summary", "match_cards", "quick_chips"]       # still composed
    assert len(agent.client.calls) == 2 and text_of(events).endswith("Here they are.")
    assert "lines up strongly" not in text_of(events)                               # no code sentence on top of the LLM's


@pytest.mark.asyncio
async def test_with_compositions_off_the_llm_chosen_card_is_just_the_card(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_compositions", False)
    agent = make_agent([[_tool_chunk("show_country_matches", {})]])
    seed(agent, **FULL)
    events = await run(agent, FREE["show_country_matches"][0])
    assert kinds(events) == ["match_cards"] and state(agent)["intent"] == "recommend_country"


@pytest.mark.asyncio
async def test_with_templated_lead_ins_off_the_llm_writes_the_sentence_again(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_template_leadins", False)
    agent = make_agent([[_tool_chunk("show_country_matches", {})], [_chunk("Here they are.")]])
    seed(agent, **FULL)
    events = await run(agent, FREE["show_country_matches"][0])
    assert kinds(events) == ["profile_summary", "match_cards", "quick_chips"]
    assert text_of(events) == "Here they are." and len(agent.client.calls) == 2


@pytest.mark.asyncio
async def test_the_tool_result_the_llm_sees_tells_it_not_to_repeat_the_buttons(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_template_leadins", False)
    agent = make_agent([[_tool_chunk("show_country_matches", {})], [_chunk("ok")]])
    seed(agent, **FULL)
    await run(agent, FREE["show_country_matches"][0])
    tool_note = next(m["content"] for m in agent.client.calls[1]["messages"] if m["role"] == "tool")
    assert "next-step buttons" in tool_note and "do not list" in tool_note


# ---- normalised arguments ----

@pytest.fixture
def catalog():
    return make_catalog()


@pytest.mark.parametrize("intent,raw,expected", [
    ("eligibility", {"country": "Australia"}, {"country": "au"}),
    ("eligibility", {"country": "au"}, {"country": "au"}),
    ("country_facts", {"country": "UK"}, {"country": "uk"}),
    ("cost_calculator", {"country": "United Kingdom"}, {"country": "uk"}),
    ("eligibility", {"country": "Atlantis"}, {}),
    ("eligibility", {}, {}),
    ("eligibility", {"country": 5}, {}),
    ("compare", {"countries": ["Canada", "U.K."]}, {"countries": ["ca", "uk"]}),
    ("compare", {"countries": ["uk", "UK", "United Kingdom", "au"]}, {"countries": ["uk", "au"]}),
    ("compare", {"countries": ["Atlantis", "au"]}, {"countries": ["au"]}),
    ("compare", {"countries": ["uk", "au", "ca"]}, {"countries": ["uk", "au", "ca"]}),
    ("compare", {}, {"countries": []}),
    ("recommend_country", {"anything": 1}, {}),
    ("profile", {}, {}),
])
def test_arguments_become_catalog_ids(catalog, intent, raw, expected):
    assert normalized_args(intent, raw, catalog) == expected


def test_a_comparison_never_keeps_more_than_three_countries():
    big = Catalog(site_id="t", countries=[c.model_copy(update={"id": f"c{i}", "label": f"Land{i}", "aliases": []}) for i, c in enumerate(make_catalog().countries * 2)])
    assert len(normalized_args("compare", {"countries": [c.id for c in big.countries]}, big)["countries"]) == 3


# ---- the miss counter: how often a message matches no rule, without ever logging what was said ----

def edu_logs(caplog):
    return [r.getMessage() for r in caplog.records if "no_rule_match" in r.getMessage()]


@pytest.mark.asyncio
async def test_a_message_no_rule_recognises_is_counted_by_length_and_language_only(caplog):
    caplog.set_level(logging.INFO, logger="zunkiree.education_agent")
    agent = make_agent([[_chunk("Noted.")]])
    await run(agent, "My secret plan is Zorblax Quantum")
    [line] = edu_logs(caplog)
    assert line == "[EDU] no_rule_match chars=33 words=6 lang=en question_like=False"
    assert not any("Zorblax" in r.getMessage() or "secret" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_a_question_and_a_romanized_nepali_message_are_labelled(caplog):
    caplog.set_level(logging.INFO, logger="zunkiree.education_agent")
    agent = make_agent(['{"shape": "none"}', [_chunk("a")], '{"shape": "none"}', [_chunk("b")]])
    await run(agent, "What is life like in Nepal?")
    await run(agent, "malai kun desh ramro cha?")
    lines = edu_logs(caplog)
    assert "lang=en question_like=True" in lines[0] and "lang=ne_romanized question_like=True" in lines[1]


@pytest.mark.asyncio
async def test_rule_matched_messages_and_taps_are_not_counted(caplog):
    caplog.set_level(logging.INFO, logger="zunkiree.education_agent")
    agent = make_agent([])
    seed(agent, **FULL)
    first = await run(agent, "Which countries fit my profile?")
    chips = next(b for b in blocks_of(first) if b["type"] == "quick_chips")
    await run(agent, "only under $25k")                                  # a follow-up, while the recommendation is on screen
    chip = chips["data"]["chips"][0]["id"]
    await run(agent, "x", block_action={"blockId": chips["block_id"], "blockType": "quick_chips", "actionId": chip,
                                         "values": {}, "displayText": "x"})
    assert edu_logs(caplog) == []
