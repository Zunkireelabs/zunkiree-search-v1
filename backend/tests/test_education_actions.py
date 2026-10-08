"""A tapped UI action is accepted only if it points at a real block from this session and asks for something that
block offered. Rejected taps are dropped (nothing applied) and the turn continues as plain typed text."""
import copy

import pytest

from app.config import get_settings
from app.services import education_agent
from app.services.education_actions import validate_block_action
from app.services.education_catalog import register_catalog
from app.services.education_memory import InMemoryEducationMemory
from app.services.education_profile import apply_updates, new_profile
from tests.test_education_agent import _chunk, blocks_of, make_agent, run
from tests.test_education_consistency import make_catalog


# ---- blocks as they are stored (model_dump shape) ----

def _block(block_type, data, actions=None, block_id="blk-1"):
    return {"block_id": block_id, "type": block_type, "schema_version": 1, "data": data, "actions": actions or []}


CHOICE = _block("choice_cards", {"field": "study_level", "multi": False,
                                 "options": [{"id": "bachelor", "label": "Bachelor's"}, {"id": "master", "label": "Master's"}]})
MULTI = _block("choice_cards", {"field": "countries", "multi": True,
                                "options": [{"id": "uk", "label": "UK"}, {"id": "au", "label": "Australia"}]})
SLIDER = _block("range_slider", {"field": "budget", "min": 20000, "max": 60000, "step": 1000, "value": 40000, "unit": "$"})
CALC = _block("cost_calculator", {"currency": "$", "parts": [
    {"id": "tuition", "label": "T", "min": 15000, "max": 25000, "step": 500, "value": 20000},
    {"id": "living", "label": "L", "min": 10000, "max": 14000, "step": 500, "value": 12000}]})
JOURNEY = _block("journey_cards", {"tiles": [{"id": "find", "title": "Find", "description": "d"},
                                             {"id": "apply", "title": "Apply", "description": "d"}]})
MATCHES = _block("match_cards", {"items": [{"id": "uk", "label": "UK", "score": 80, "reasons": []}]})
FORM = _block("lead_form", {"fields": [{"id": "name", "label": "N", "type": "text"}, {"id": "email", "label": "E", "type": "email"}]})
PROFILE = _block("profile_summary", {"rows": [{"label": "Budget", "value": "x"}]}, actions=[{"id": "edit", "label": "Update"}])
CHIPS = _block("quick_chips", {"chips": [{"id": "visa", "label": "Visa"}]})
STEPPER = _block("stepper", {"steps": [{"title": "a"}, {"title": "b"}]})


def tap(block, action_id, values=None):
    return {"blockId": block["block_id"], "blockType": block["type"], "actionId": action_id, "values": values or {}, "displayText": "t"}


# ---- valid taps (exactly what the widget sends) ----

@pytest.mark.parametrize("block,action", [
    (CHOICE, tap(CHOICE, "select", {"field": "study_level", "selected": ["master"]})),
    (MULTI, tap(MULTI, "select", {"field": "countries", "selected": ["uk", "au"]})),
    (MULTI, tap(MULTI, "select", {"field": "countries", "selected": []})),
    (SLIDER, tap(SLIDER, "set_value", {"field": "budget", "value": 35000})),
    (SLIDER, tap(SLIDER, "set_value", {"field": "budget", "value": 20000})),
    (SLIDER, tap(SLIDER, "set_value", {"field": "budget", "value": 60000})),
    (CALC, tap(CALC, "set_value", {"field": "budget", "value": 31000})),
    (JOURNEY, tap(JOURNEY, "start", {"journey": "apply"})),
    (MATCHES, tap(MATCHES, "explore", {"country": "uk"})),
    (FORM, tap(FORM, "submit", {"name": "A", "email": "a@b.co"})),
    (FORM, tap(FORM, "submit", {"name": "", "email": ""})),
    (PROFILE, tap(PROFILE, "edit")),
    (CHIPS, tap(CHIPS, "visa")),
])
def test_valid_taps_pass(block, action):
    assert validate_block_action(action, block) is None


# ---- rejected taps ----

@pytest.mark.parametrize("action,block,reason", [
    (None, None, "malformed"),
    ("select", CHOICE, "malformed"),
    ({"blockId": "", "blockType": "choice_cards", "actionId": "select"}, CHOICE, "malformed"),
    ({"blockId": "blk-1", "blockType": "choice_cards", "actionId": "select", "values": "x"}, CHOICE, "malformed"),
    ({"blockId": 5, "blockType": "choice_cards", "actionId": "select"}, CHOICE, "malformed"),
    (tap(CHOICE, "select", {"field": "study_level", "selected": ["master"]}), None, "unknown_block"),
    ({**tap(CHOICE, "select", {"field": "study_level", "selected": ["master"]}), "blockType": "range_slider"}, CHOICE, "type_mismatch"),
    (tap(STEPPER, "select", {"field": "x", "selected": ["a"]}), STEPPER, "action_not_offered"),
    (tap(SLIDER, "select", {"field": "budget", "selected": ["a"]}), SLIDER, "action_not_offered"),
    (tap(CHOICE, "submit", {"name": "A"}), CHOICE, "action_not_offered"),
    (tap(CHIPS, "not-a-chip"), CHIPS, "action_not_offered"),
    (tap(PROFILE, "delete_everything"), PROFILE, "action_not_offered"),
    # values that do not fit the block
    (tap(CHOICE, "select", {"field": "countries", "selected": ["master"]}), CHOICE, "wrong_field"),
    (tap(CHOICE, "select", {"field": "study_level", "selected": ["phd"]}), CHOICE, "not_an_option"),
    (tap(CHOICE, "select", {"field": "study_level", "selected": ["bachelor", "master"]}), CHOICE, "too_many_selected"),
    (tap(CHOICE, "select", {"field": "study_level", "selected": "master"}), CHOICE, "bad_values"),
    (tap(CHOICE, "select", {"field": "study_level", "selected": [7]}), CHOICE, "bad_values"),
    (tap(SLIDER, "set_value", {"field": "study_level", "value": 30000}), SLIDER, "wrong_field"),
    (tap(SLIDER, "set_value", {"field": "budget", "value": -5}), SLIDER, "out_of_range"),
    (tap(SLIDER, "set_value", {"field": "budget", "value": 19999}), SLIDER, "out_of_range"),
    (tap(SLIDER, "set_value", {"field": "budget", "value": 60001}), SLIDER, "out_of_range"),
    (tap(SLIDER, "set_value", {"field": "budget", "value": "30000"}), SLIDER, "bad_values"),
    (tap(SLIDER, "set_value", {"field": "budget", "value": True}), SLIDER, "bad_values"),
    (tap(SLIDER, "set_value", {"field": "budget", "value": float("nan")}), SLIDER, "bad_values"),
    (tap(CALC, "set_value", {"field": "english_score", "value": 31000}), CALC, "wrong_field"),
    (tap(CALC, "set_value", {"field": "budget", "value": 24999}), CALC, "out_of_range"),
    (tap(CALC, "set_value", {"field": "budget", "value": 39001}), CALC, "out_of_range"),
    (tap(JOURNEY, "start", {"journey": "hack"}), JOURNEY, "not_an_option"),
    (tap(JOURNEY, "start", {}), JOURNEY, "not_an_option"),
    (tap(MATCHES, "explore", {"country": "atlantis"}), MATCHES, "not_an_option"),
    (tap(FORM, "submit", {"name": "A", "role": "admin"}), FORM, "wrong_field"),
    (tap(FORM, "submit", {"name": 5}), FORM, "bad_values"),
])
def test_invalid_taps_are_rejected_with_a_reason(action, block, reason):
    assert validate_block_action(action, block) == reason


def test_every_action_a_registered_type_allows_has_a_value_check():
    from app.schemas.ui_blocks import UI_TYPES
    from app.services.education_actions import _VALUE_CHECKS
    # 'edit' and quick-chip ids carry no values the agent uses; everything else must be value-checked.
    unchecked = {a for s in UI_TYPES.values() for a in s.allowed_actions} - set(_VALUE_CHECKS)
    assert unchecked <= {"edit"}, unchecked


# ---- finding the originating block ----

@pytest.mark.asyncio
async def test_find_block_searches_only_this_sessions_assistant_messages():
    memory = InMemoryEducationMemory()
    await memory.append_message(None, "s1", "assistant", "hi", [CHOICE])
    await memory.append_message(None, "s2", "assistant", "hi", [SLIDER])
    await memory.append_message(None, "s1", "user", "yo", [MATCHES])
    assert await memory.find_block(None, "s1", "blk-1") == CHOICE
    assert await memory.find_block(None, "s1", "nope") is None
    assert await memory.find_block(None, "s3", "blk-1") is None


@pytest.mark.asyncio
async def test_find_block_ignores_blocks_older_than_the_window():
    memory = InMemoryEducationMemory()
    await memory.append_message(None, "s1", "assistant", "old", [CHOICE])
    for i in range(50):
        await memory.append_message(None, "s1", "user", f"m{i}")
    assert await memory.find_block(None, "s1", "blk-1") is None


# ---- agent flow (validation switched ON explicitly) ----

@pytest.fixture(autouse=True)
def _validation_on(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_validate_block_actions", True)
    cat = make_catalog()
    cat.site_id = "edu-agent-test"
    register_catalog(cat)


def test_validation_is_on_by_default():
    assert get_settings().model_fields["education_validate_block_actions"].default is True


async def _agent_after_first_card(script):
    agent = make_agent(script)
    [first] = blocks_of(await run(agent, "Which countries fit my profile?"))   # persists a real match_cards block
    return agent, first


def _seed(agent, **fields):
    p = new_profile()
    apply_updates(p, fields)
    agent.memory.profiles[(None, "s1")] = p


@pytest.mark.asyncio
async def test_a_genuine_tap_on_a_shown_block_is_applied_as_before():
    agent = make_agent([[_chunk("Welcome.")], [_chunk("Here you go.")]])
    [welcome] = blocks_of(await run(agent, "hello"))
    events = await run(agent, "Find the right country", block_action=tap(welcome, "start", {"journey": "find"}))
    [pick] = blocks_of(events)
    assert pick["type"] == "choice_cards" and pick["data"]["field"] == "countries"   # the journey really started


@pytest.mark.asyncio
async def test_a_fabricated_block_id_changes_nothing_and_the_turn_continues_as_text(caplog):
    agent = make_agent([[_chunk("Sure.")]])
    forged = {"blockId": "made-up", "blockType": "range_slider", "actionId": "set_value",
              "values": {"field": "budget", "value": 1}, "displayText": "hello there"}
    with caplog.at_level("WARNING"):
        events = await run(agent, "hello there", block_action=forged)
    profile = agent.memory.profiles.get((None, "s1")) or new_profile()
    assert not profile.get("budget")
    assert events[-1]["type"] == "done"
    assert any("rejected block_action reason=unknown_block" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_an_out_of_range_value_on_a_real_block_is_not_stored():
    from app.services.education_tools import execute_education_tool
    agent = make_agent([[_chunk("ok")]])
    _seed(agent, countries=["uk"])
    slider = execute_education_tool("show_budget_slider", {}, agent.memory.profiles[(None, "s1")], make_catalog()).block
    await agent.memory.append_message(None, "s1", "assistant", "Budget?", [slider.model_dump()])

    bad = {"blockId": slider.block_id, "blockType": "range_slider", "actionId": "set_value",
           "values": {"field": "budget", "value": 9_999_999}, "displayText": "My budget is huge"}
    await run(agent, "My budget is huge", block_action=bad)
    assert not agent.memory.profiles[(None, "s1")].get("budget")


@pytest.mark.asyncio
async def test_a_rejected_tap_never_marks_the_block_answered():
    agent = make_agent([[_chunk("Welcome.")], [_chunk("ok")]])
    [welcome] = blocks_of(await run(agent, "hello"))
    await run(agent, "x", block_action=tap(welcome, "start", {"journey": "nonsense"}))
    stored = await agent.memory.find_block(None, "s1", welcome["block_id"])
    assert stored.get("answered") is None


@pytest.mark.asyncio
async def test_with_validation_off_the_previous_behaviour_returns(monkeypatch):
    monkeypatch.setattr(education_agent.settings, "education_validate_block_actions", False)
    agent = make_agent([[_chunk("ok")]])
    forged = {"blockId": "made-up", "blockType": "choice_cards", "actionId": "select",
              "values": {"field": "study_level", "selected": ["master"]}, "displayText": "Master's"}
    await run(agent, "Master's", block_action=forged)
    assert agent.memory.profiles[(None, "s1")]["study_level"] == "master"


def test_validate_does_not_mutate_its_inputs():
    action, block = tap(CHOICE, "select", {"field": "study_level", "selected": ["master"]}), copy.deepcopy(CHOICE)
    before = copy.deepcopy((action, block))
    validate_block_action(action, block)
    assert (action, block) == before
