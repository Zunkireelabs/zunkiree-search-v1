"""Compositions: a result card shown with its companions (profile summary, next-step buttons) as a fixed recipe per intent.
Same intent + same state -> same blocks. Buttons come from a closed set and are offered only when the card they lead to can
actually be built; a tap resolves in code, never through the LLM."""
import copy
import json
import os
from pathlib import Path

import pytest

from app.services import education_agent
from app.services.education_catalog import Catalog, CountryRecord, register_catalog
from app.services.education_compositions import (
    COMPOSITIONS, MAX_CHIPS, chip_intent, chip_label, compose, counselor_block,
)
from app.services.education_profile import apply_updates, new_profile
from app.services.education_tools import execute_education_tool, tool_for_intent
from app.services.education_ui_registry import INTENTS
from tests.test_education_agent import PROCESS_CHUNKS, _chunk, blocks_of, make_agent, run, types
from tests.test_education_consistency import make_catalog

GOLDEN = Path(__file__).parent / "golden" / "education_compositions.json"
FULL = dict(budget=40000, english_score=6.5, academic_score=70, intake="September")


@pytest.fixture
def catalog():
    return make_catalog()


def profile_with(**fields) -> dict:
    p = new_profile()
    apply_updates(p, fields)
    return p


def composed(intent, args, catalog, **fields):
    p = profile_with(**fields)
    out = execute_education_tool(tool_for_intent(intent), dict(args), p, catalog)
    return compose(intent, args, out.block, p, catalog), p


def kinds(blocks):
    return [b.type for b in blocks]


def chip_ids(blocks):
    return [c["id"] for b in blocks if b.type == "quick_chips" for c in b.data["chips"]]


# ---- the recipes ----

@pytest.mark.parametrize("intent,args,expected", [
    ("recommend_country", {}, ["profile_summary", "match_cards", "quick_chips"]),
    ("compare", {"countries": ["uk", "au"]}, ["comparison_table", "quick_chips"]),
    ("eligibility", {"country": "uk"}, ["eligibility_meter", "quick_chips"]),
    ("country_facts", {"country": "uk"}, ["info_card", "quick_chips"]),
    ("cost_calculator", {"country": "uk"}, ["cost_calculator", "quick_chips"]),
    ("profile", {}, ["profile_summary", "quick_chips"]),
])
def test_each_result_intent_has_its_fixed_recipe(catalog, intent, args, expected):
    blocks, _ = composed(intent, args, catalog, **FULL)
    assert kinds(blocks) == expected


@pytest.mark.parametrize("intent,args", [("welcome", {}), ("choice", {"kind": "countries"}), ("budget", {}), ("lead_form", {})])
def test_guided_and_input_cards_have_no_companions(catalog, intent, args):
    blocks, _ = composed(intent, args, catalog, **FULL)
    assert len(blocks) == 1


def test_the_recipe_table_only_uses_known_parts_and_registered_intents():
    for intent, parts in COMPOSITIONS.items():
        assert intent in INTENTS and "primary" in parts
        assert set(parts) <= {"primary", "profile", "next_steps"}


def test_the_primary_block_is_returned_untouched(catalog):
    p = profile_with(**FULL)
    primary = execute_education_tool("show_country_facts", {"country": "uk"}, p, catalog).block
    assert compose("country_facts", {"country": "uk"}, primary, p, catalog)[0] is primary


def test_the_same_state_gives_the_same_blocks_and_ids(catalog):
    runs = [[b.model_dump() for b in composed("recommend_country", {}, catalog, **FULL)[0]] for _ in range(4)]
    assert all(r == runs[0] for r in runs)


def test_every_composed_block_is_a_valid_registered_block(catalog):
    from app.schemas.ui_blocks import UI_TYPES
    for intent, args in [("recommend_country", {}), ("compare", {"countries": ["uk", "au"]}), ("eligibility", {"country": "uk"})]:
        for block in composed(intent, args, catalog, **FULL)[0]:
            assert block.type in UI_TYPES and block.schema_version == UI_TYPES[block.type].version and block.fallback_text


# ---- the closed set of buttons ----

@pytest.mark.parametrize("chip,expected", [
    ("matches", ("recommend_country", {})), ("profile", ("profile", {})), ("budget", ("budget", {})), ("lead", ("lead_form", {})),
    ("eligibility:uk", ("eligibility", {"country": "uk"})), ("cost:au", ("cost_calculator", {"country": "au"})),
    ("facts:ca", ("country_facts", {"country": "ca"})),
    ("compare:uk+au", ("compare", {"countries": ["uk", "au"]})),
    ("compare:uk+au+ca", ("compare", {"countries": ["uk", "au", "ca"]})),
])
def test_valid_button_ids_resolve_to_an_intent(catalog, chip, expected):
    assert chip_intent(chip, catalog) == expected


@pytest.mark.parametrize("chip", [
    "", "nope", "eligibility:", "eligibility:atlantis", "Eligibility:uk", " eligibility:uk", "eligibility:uk ", "matches:uk",
    "lead:x", "compare:uk", "compare:uk+uk", "compare:uk+atlantis", "compare:", "compare:uk+au+ca+us", "cost:uk+au", "facts:",
    "../etc/passwd", "eligibility:uk;drop", "recommend_country",
])
def test_anything_else_resolves_to_nothing(catalog, chip):
    assert chip_intent(chip, catalog) is None


def test_button_labels_are_plain_words(catalog):
    assert chip_label("eligibility:uk", catalog) == "Check my eligibility for U.K."
    assert chip_label("cost:au", catalog) == "Estimate costs for Australia"
    assert chip_label("compare:uk+au", catalog) == "Compare U.K. and Australia"
    assert chip_label("lead", catalog) == "Talk to a counselor"


def test_every_offered_button_resolves_and_has_a_label(catalog):
    for intent, args in [("recommend_country", {}), ("compare", {"countries": ["uk", "au"]}), ("eligibility", {"country": "au"}),
                         ("country_facts", {"country": "ca"}), ("cost_calculator", {"country": "uk"}), ("profile", {})]:
        blocks, _ = composed(intent, args, catalog, **FULL)
        for block in blocks:
            if block.type == "quick_chips":
                assert 1 <= len(block.data["chips"]) <= MAX_CHIPS
                for chip in block.data["chips"]:
                    assert chip_intent(chip["id"], catalog) and chip["label"] == chip_label(chip["id"], catalog)


# ---- which buttons follow which card ----

def test_recommendations_suggest_comparing_the_top_two_and_checking_the_first(catalog):
    blocks, _ = composed("recommend_country", {}, catalog, **FULL)
    assert chip_ids(blocks) == ["compare:uk+ca", "eligibility:uk", "cost:uk"]     # Australia is only a Possible fit


@pytest.mark.parametrize("intent,args,expected", [
    ("compare", {"countries": ["uk", "au"]}, ["eligibility:uk", "cost:uk", "lead"]),
    ("eligibility", {"country": "uk"}, ["cost:uk", "matches", "lead"]),
    ("country_facts", {"country": "uk"}, ["eligibility:uk", "cost:uk", "matches"]),
    ("cost_calculator", {"country": "uk"}, ["eligibility:uk", "facts:uk", "lead"]),
    ("profile", {}, ["matches", "budget", "lead"]),
])
def test_next_steps_per_card(catalog, intent, args, expected):
    assert chip_ids(composed(intent, args, catalog, **FULL)[0]) == expected


def test_a_button_is_never_offered_for_the_card_just_shown(catalog):
    assert "cost:uk" not in chip_ids(composed("cost_calculator", {"country": "uk"}, catalog, **FULL)[0])
    assert "eligibility:uk" not in chip_ids(composed("eligibility", {"country": "uk"}, catalog, **FULL)[0])


# ---- nothing is offered that can't be delivered ----

def test_no_eligibility_button_without_scores(catalog):
    assert "eligibility:uk" not in chip_ids(composed("country_facts", {"country": "uk"}, catalog, budget=40000)[0])
    assert "eligibility:uk" in chip_ids(composed("country_facts", {"country": "uk"}, catalog, english_score=6.5)[0])


def test_no_compare_button_with_fewer_than_two_countries():
    one = Catalog(site_id="t", countries=[make_catalog().countries[0]])
    blocks, _ = composed("recommend_country", {}, one, **FULL)
    assert not any(c.startswith("compare:") for c in chip_ids(blocks))


def test_no_cost_button_for_a_country_without_cost_figures():
    bare = Catalog(site_id="t", countries=[CountryRecord(id="uk", label="U.K.", ielts_min=6.5, intakes=["September"])])
    blocks, _ = composed("country_facts", {"country": "uk"}, bare, english_score=6.5)
    assert "cost:uk" not in chip_ids(blocks)


def test_countries_that_need_review_are_never_suggested(catalog):
    blocks, _ = composed("recommend_country", {}, catalog, budget=40000, english_score=3, academic_score=70)
    assert chip_ids(blocks) == ["budget"]          # every country fails the English minimum: nothing to compare or check


def test_probing_a_button_leaves_no_trace_in_the_students_profile(catalog):
    _, p = composed("recommend_country", {}, catalog, **FULL)
    assert set(p["shown"]) == {"recommend_country:all", "profile:all"}


def test_a_profile_with_nothing_in_it_gets_no_profile_summary_and_no_hollow_buttons(catalog):
    p = new_profile()
    blocks = compose("country_facts", {"country": "uk"},
                     execute_education_tool("show_country_facts", {"country": "uk"}, p, catalog).block, p, catalog)
    assert "profile_summary" not in kinds(blocks)
    assert "profile:" not in "".join(chip_ids(blocks))


# ---- counselor button on a knowledge-base miss ----

def test_the_counselor_block_is_one_lead_button(catalog):
    block = counselor_block(catalog)
    assert block.type == "quick_chips" and [c["id"] for c in block.data["chips"]] == ["lead"]


# ---- golden snapshot of the composed turns ----

def _golden_cases(catalog):
    out = {}
    for intent, args in [("recommend_country", {}), ("compare", {"countries": ["uk", "au"]}), ("eligibility", {"country": "uk"}),
                         ("country_facts", {"country": "uk"}), ("cost_calculator", {"country": "uk"}), ("profile", {})]:
        out[intent] = [b.model_dump() for b in composed(intent, args, catalog, **FULL)[0]]
    out["recommend_country_budget_only"] = [b.model_dump() for b in composed("recommend_country", {}, catalog, budget=40000)[0]]
    return json.loads(json.dumps(out, sort_keys=True, default=str))


def test_composed_turns_match_the_golden_file(catalog):
    built = _golden_cases(catalog)
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(built, indent=2, sort_keys=True) + "\n")
        pytest.skip("golden file regenerated")
    golden = json.loads(GOLDEN.read_text())
    assert built.keys() == golden.keys()
    for name in golden:
        assert built[name] == golden[name], f"composition '{name}' no longer matches its golden snapshot"


# ---- agent flow (compositions and tap validation both ON, as in production) ----

@pytest.fixture(autouse=True)
def _agent_catalog():
    cat = make_catalog()
    cat.site_id = "edu-agent-test"
    register_catalog(cat)


def seed(agent, **fields):
    agent.memory.profiles[(None, "s1")] = profile_with(**fields)


def chip_tap(block, chip_id):
    label = next(c["label"] for c in block["data"]["chips"] if c["id"] == chip_id)
    return {"blockId": block["block_id"], "blockType": "quick_chips", "actionId": chip_id, "values": {"chip": chip_id}, "displayText": label}


def chips_of(events):
    return next(b for b in blocks_of(events) if b["type"] == "quick_chips")


@pytest.mark.asyncio
async def test_a_recommendation_turn_streams_the_composition_in_order_with_no_llm_tools():
    agent = make_agent([[_chunk("Here is how they line up.")]])
    seed(agent, **FULL)
    events = await run(agent, "Which countries fit my profile?")
    assert [b["type"] for b in blocks_of(events)] == ["profile_summary", "match_cards", "quick_chips"]
    assert "tools" not in agent.client.calls[0]
    agent.query_service._retrieve_and_rank.assert_not_awaited()
    note = " ".join(m["content"] for m in agent.client.calls[0]["messages"] if m["role"] == "system")
    assert "next-step buttons" in note and "do not list" in note
    assert types(events)[-1] == "done"


@pytest.mark.asyncio
async def test_the_whole_composition_is_saved_so_a_reload_restores_it():
    agent = make_agent([[_chunk("ok")]])
    seed(agent, **FULL)
    await run(agent, "Which countries fit my profile?")
    [_, assistant] = await agent.memory.list_messages(None, "s1")
    assert [b["type"] for b in assistant["blocks"]] == ["profile_summary", "match_cards", "quick_chips"]


@pytest.mark.asyncio
async def test_tapping_a_button_shows_that_card_without_the_llm_deciding_anything():
    agent = make_agent([[_chunk("Here.")], [_chunk("And your eligibility:")]])
    seed(agent, **FULL)
    chips = chips_of(await run(agent, "Which countries fit my profile?"))
    events = await run(agent, "x", block_action=chip_tap(chips, "eligibility:uk"))
    shown = blocks_of(events)
    assert [b["type"] for b in shown] == ["eligibility_meter", "quick_chips"] and shown[0]["title"] == "U.K. eligibility"
    assert "tools" not in agent.client.calls[1]
    agent.query_service._retrieve_and_rank.assert_not_awaited()
    assert agent.memory.profiles[(None, "s1")]["ui_state"]["intent"] == "eligibility"


@pytest.mark.asyncio
async def test_a_compare_button_opens_the_comparison():
    agent = make_agent([[_chunk("a")], [_chunk("b")]])
    seed(agent, **FULL)
    chips = chips_of(await run(agent, "Which countries fit my profile?"))
    [table, _] = blocks_of(await run(agent, "x", block_action=chip_tap(chips, "compare:uk+ca")))
    assert table["type"] == "comparison_table" and [c["id"] for c in table["data"]["columns"]] == ["uk", "ca"]


@pytest.mark.asyncio
async def test_the_cost_and_counselor_buttons_open_their_cards():
    agent = make_agent([[_chunk("a")], [_chunk("b")], [_chunk("c")], [_chunk("d")]])
    seed(agent, **FULL)
    first = chips_of(await run(agent, "Which countries fit my profile?"))
    calculator = blocks_of(await run(agent, "x", block_action=chip_tap(first, "cost:uk")))[0]
    assert calculator["type"] == "cost_calculator" and calculator["title"] == "U.K. cost calculator"
    profile_chips = chips_of(await run(agent, "What do you know about me?"))
    [form] = blocks_of(await run(agent, "x", block_action=chip_tap(profile_chips, "lead")))
    assert form["type"] == "lead_form"


@pytest.mark.asyncio
async def test_a_forged_button_id_is_rejected_by_tap_validation_and_treated_as_text(caplog):
    agent = make_agent([[_chunk("ok")], [_chunk("Sorry.")]])
    seed(agent, **FULL)
    chips = chips_of(await run(agent, "Which countries fit my profile?"))
    forged = {**chip_tap(chips, "cost:uk"), "actionId": "eligibility:au", "values": {"chip": "eligibility:au"}}   # not a button on that card
    before = copy.deepcopy(agent.memory.profiles[(None, "s1")]["ui_state"])
    with caplog.at_level("WARNING"):
        events = await run(agent, "just some words", block_action=forged)
    assert any("rejected block_action reason=action_not_offered" in r.getMessage() for r in caplog.records)
    assert events[-1]["type"] == "done"
    assert all(b["type"] != "eligibility_meter" for b in blocks_of(events))                # the forged button opened nothing
    assert agent.memory.profiles[(None, "s1")]["ui_state"] == before          # the tap changed nothing


@pytest.mark.asyncio
async def test_a_follow_up_after_a_button_keeps_working():
    agent = make_agent([[_chunk("a")], [_chunk("b")], [_chunk("c")]])
    seed(agent, **FULL)
    chips = chips_of(await run(agent, "Which countries fit my profile?"))
    await run(agent, "x", block_action=chip_tap(chips, "eligibility:uk"))
    shown = blocks_of(await run(agent, "what about Canada?"))
    assert shown[0]["title"] == "Canada eligibility" and shown[-1]["type"] == "quick_chips"


@pytest.mark.asyncio
async def test_a_knowledge_base_miss_offers_the_counselor_button_and_it_opens_the_form():
    agent = make_agent([json.dumps({"found": False}), [_chunk("I don't have those details; a counselor can help.")], [_chunk("Fill this in.")]],
                       chunks=PROCESS_CHUNKS)
    events = await run(agent, "What is the application process?")
    [chips] = blocks_of(events)
    assert chips["type"] == "quick_chips" and [c["id"] for c in chips["data"]["chips"]] == ["lead"]
    [form] = blocks_of(await run(agent, "x", block_action=chip_tap(chips, "lead")))
    assert form["type"] == "lead_form"


@pytest.mark.asyncio
async def test_with_compositions_off_a_turn_shows_just_the_card(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_compositions", False)
    agent = make_agent([[_chunk("Here.")]])
    seed(agent, **FULL)
    assert [b["type"] for b in blocks_of(await run(agent, "Which countries fit my profile?"))] == ["match_cards"]


def test_compositions_are_on_by_default():
    from app.config import Settings
    assert Settings.model_fields["education_compositions"].default is True
