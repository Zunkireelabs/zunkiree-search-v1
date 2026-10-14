"""Versioned blocks: a block stored at an older UI version is upgraded when a chain exists, otherwise rebuilt or shown as
plain text, and never served in a shape the current code doesn't expect. No real type has a v2 yet, so each test injects
a temporary newer spec into the registry."""
import copy
from dataclasses import replace

import pytest

from app.schemas.ui_blocks import UI_TYPES, build_block, is_current, upgrade_stored_block
from app.services import education_kb_blocks as kb
from app.services.education_actions import validate_block_action
from app.services.education_kb_blocks import kb_block
from app.services.education_memory import InMemoryEducationMemory
from app.services.education_profile import apply_updates, new_profile
from app.services.education_tools import execute_education_tool
from tests.test_education_consistency import make_catalog
from tests.test_education_kb_blocks import CHUNKS, GOOD_STEPS, FakeClient


def bump(monkeypatch, block_type, version, upgraders=None):
    monkeypatch.setitem(UI_TYPES, block_type, replace(UI_TYPES[block_type], version=version, upgraders=upgraders or {}))


def stepper_v1(**extra):
    """A stored v1 stepper, whatever the registry currently says (build_block stamps the registry's version)."""
    block = build_block("stepper", {"steps": [{"title": "One"}, {"title": "Two"}]},
                        fallback_text="One, Two", title="Steps").model_dump()
    return {**block, "schema_version": 1, **extra}


def add_detail(data):   # a plausible v1 -> v2 change
    return {**data, "steps": [{**s, "detail": s.get("detail") or "see counselor"} for s in data["steps"]]}


def shout(data):        # a plausible v2 -> v3 change
    return {**data, "steps": [{**s, "title": s["title"].upper()} for s in data["steps"]]}


# ---- upgrade_stored_block ----

def test_a_current_block_is_returned_untouched():
    block = stepper_v1()
    assert upgrade_stored_block(block) is block and is_current(block)


def test_an_older_block_is_upgraded_keeping_its_identity_and_text(monkeypatch):
    bump(monkeypatch, "stepper", 2, {1: add_detail})
    block = stepper_v1()
    before = copy.deepcopy(block)
    up = upgrade_stored_block(block)
    assert up["schema_version"] == 2 and is_current(up) and not is_current(block)
    assert up["data"]["steps"][0]["detail"] == "see counselor"
    assert (up["block_id"], up["title"], up["fallback_text"]) == (block["block_id"], block["title"], block["fallback_text"])
    assert block == before                                    # the input is never mutated


def test_a_chain_is_applied_in_order(monkeypatch):
    bump(monkeypatch, "stepper", 3, {1: add_detail, 2: shout})
    up = upgrade_stored_block(stepper_v1())
    assert up["schema_version"] == 3
    assert [s["title"] for s in up["data"]["steps"]] == ["ONE", "TWO"] and up["data"]["steps"][0]["detail"] == "see counselor"


def test_a_block_from_the_middle_of_the_chain_only_runs_the_remaining_steps(monkeypatch):
    bump(monkeypatch, "stepper", 3, {1: add_detail, 2: shout})
    up = upgrade_stored_block(stepper_v1(schema_version=2))
    assert up["schema_version"] == 3
    assert [s["title"] for s in up["data"]["steps"]] == ["ONE", "TWO"]        # the v2 -> v3 step ran
    assert "detail" not in up["data"]["steps"][0]                             # the v1 -> v2 step did not


def test_a_missing_step_leaves_the_block_unchanged(monkeypatch):
    bump(monkeypatch, "stepper", 3, {2: shout})                # nothing upgrades v1 -> v2
    block = stepper_v1()
    assert upgrade_stored_block(block) is block


def test_an_upgrader_that_raises_leaves_the_block_unchanged(monkeypatch):
    def boom(data):
        raise KeyError("nope")
    bump(monkeypatch, "stepper", 2, {1: boom})
    block = stepper_v1()
    assert upgrade_stored_block(block) is block


def test_an_upgrade_that_fails_the_current_schema_is_discarded(monkeypatch):
    bump(monkeypatch, "stepper", 2, {1: lambda d: {"steps": []}})   # a stepper needs at least 2 steps
    block = stepper_v1()
    assert upgrade_stored_block(block) is block


def test_a_block_newer_than_this_backend_is_left_alone():
    block = stepper_v1(schema_version=5)
    assert upgrade_stored_block(block) is block and not is_current(block)


@pytest.mark.parametrize("block", [
    {"type": "hologram_card", "schema_version": 1, "data": {}},
    {"type": ["stepper"], "schema_version": 1, "data": {}},
    {"schema_version": 1, "data": {}},
])
def test_unknown_or_malformed_types_are_left_alone(block):
    assert upgrade_stored_block(block) is block and not is_current(block)


def test_a_block_with_no_version_is_v1():
    block = stepper_v1()
    del block["schema_version"]
    assert is_current(block) and upgrade_stored_block(block) is block


@pytest.mark.parametrize("version", ["1", True, None, 1.5])
def test_a_nonsense_version_is_never_treated_as_current(version):
    block = stepper_v1(schema_version=version)
    assert not is_current(block) and upgrade_stored_block(block) is block


def test_new_blocks_carry_the_registry_version(monkeypatch):
    bump(monkeypatch, "stepper", 2, {1: add_detail})
    assert build_block("stepper", {"steps": [{"title": "a"}, {"title": "b"}]}, fallback_text="x").schema_version == 2


# ---- stored blocks are upgraded wherever they are read back ----

@pytest.mark.asyncio
async def test_history_and_block_lookup_return_upgraded_blocks_without_rewriting_the_store(monkeypatch):
    bump(monkeypatch, "stepper", 2, {1: add_detail})
    memory = InMemoryEducationMemory()
    old = stepper_v1()
    await memory.append_message(None, "s1", "assistant", "hi", [old])

    [msg] = await memory.list_messages(None, "s1")
    assert msg["blocks"][0]["schema_version"] == 2 and msg["blocks"][0]["data"]["steps"][0]["detail"] == "see counselor"
    assert (await memory.find_block(None, "s1", old["block_id"]))["schema_version"] == 2
    assert memory.messages[(None, "s1")][0]["blocks"][0]["schema_version"] == 1      # stored copy untouched


@pytest.mark.asyncio
async def test_a_tap_on_an_upgraded_block_is_validated_against_the_upgraded_data(monkeypatch):
    v1 = build_block("choice_cards", {"field": "study_level", "multi": False,
                                      "options": [{"id": "bach", "label": "Bachelor's"}, {"id": "mast", "label": "Master's"}]},
                     fallback_text="x").model_dump()

    def rename_ids(data):
        ids = {"bach": "bachelor", "mast": "master"}
        return {**data, "options": [{**o, "id": ids[o["id"]]} for o in data["options"]]}

    bump(monkeypatch, "choice_cards", 2, {1: rename_ids})
    memory = InMemoryEducationMemory()
    await memory.append_message(None, "s1", "assistant", "hi", [v1])
    tap = {"blockId": v1["block_id"], "blockType": "choice_cards", "actionId": "select",
           "values": {"field": "study_level", "selected": ["master"]}, "displayText": "Master's"}

    assert validate_block_action(tap, await memory.find_block(None, "s1", v1["block_id"])) is None   # what the widget shows
    assert validate_block_action(tap, v1) == "not_an_option"                                         # the stale stored shape


# ---- caches ----

def _facts_profile():
    p = new_profile()
    apply_updates(p, {"budget": 40000})
    return p


def test_a_cached_result_block_is_upgraded_not_served_stale(monkeypatch):
    catalog, profile = make_catalog(), _facts_profile()
    first = execute_education_tool("show_country_facts", {"country": "uk"}, profile, catalog).block
    bump(monkeypatch, "info_card", 2, {1: lambda d: d})
    again = execute_education_tool("show_country_facts", {"country": "uk"}, profile, catalog).block
    assert again.schema_version == 2 and again.block_id == first.block_id and again.data == first.data
    assert again.changed_because is None


def test_a_cached_result_block_with_no_upgrade_path_is_rebuilt_at_the_current_version(monkeypatch):
    catalog, profile = make_catalog(), _facts_profile()
    first = execute_education_tool("show_country_facts", {"country": "uk"}, profile, catalog).block
    bump(monkeypatch, "info_card", 2)                          # no upgraders
    again = execute_education_tool("show_country_facts", {"country": "uk"}, profile, catalog).block
    assert again.schema_version == 2 and again.data == first.data and again.changed_because is None
    assert profile["shown"]["country_facts:uk"]["block"]["schema_version"] == 2   # the fresh block replaced the stale one


@pytest.fixture
def clean_kb_cache():
    kb._llm_shape_cache.clear()
    kb._shared_cache.clear()
    yield
    kb._shared_cache.clear()


@pytest.mark.asyncio
async def test_a_cached_knowledge_base_block_is_upgraded_without_another_extraction(monkeypatch, clean_kb_cache):
    client, profile = FakeClient([GOOD_STEPS]), new_profile()
    first = await kb_block(client, "m", profile, "process", "q", CHUNKS)
    bump(monkeypatch, "stepper", 2, {1: add_detail})
    again = await kb_block(client, "m", profile, "process", "q", CHUNKS)
    assert len(client.calls) == 1                              # no second LLM call
    assert again.schema_version == 2 and again.block_id == first.block_id


@pytest.mark.asyncio
async def test_a_cached_knowledge_base_block_with_no_upgrade_path_is_extracted_again(monkeypatch, clean_kb_cache):
    client, profile = FakeClient([GOOD_STEPS, GOOD_STEPS]), new_profile()
    await kb_block(client, "m", profile, "process", "q", CHUNKS)
    bump(monkeypatch, "stepper", 2)
    again = await kb_block(client, "m", profile, "process", "q", CHUNKS)
    assert len(client.calls) == 2 and again.schema_version == 2
