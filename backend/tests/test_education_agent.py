"""Education agent turn flow with a fake LLM: code-built blocks stream as ui_block
before the lead-in text, taps update the profile without the LLM, free-form turns
use the tool loop, and nothing is shown when the data isn't there."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.education_agent import EducationAgentService
from app.services.education_catalog import Catalog, register_catalog
from app.services.education_memory import InMemoryEducationMemory
from tests.test_education_consistency import make_catalog


def _chunk(content=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=content, tool_calls=tool_calls))])


def _tool_chunk(name, args, call_id="call_1"):
    fn = SimpleNamespace(name=name, arguments=json.dumps(args))
    return _chunk(tool_calls=[SimpleNamespace(index=0, id=call_id, function=fn)])


class FakeLLM:
    """Each create() call pops the next scripted response (a list of chunks)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        chunks = self.script.pop(0)
        if isinstance(chunks, str):  # a non-streaming reply (shape classification / knowledge-base extraction)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=chunks))])

        async def gen():
            for c in chunks:
                yield c
        return gen()


def make_agent(script, chunks=None):
    agent = EducationAgentService.__new__(EducationAgentService)
    agent.client = FakeLLM(script)
    agent.model = "test"
    agent.memory = InMemoryEducationMemory()
    agent.memory_for = lambda db: agent.memory
    agent.query_service = SimpleNamespace(_retrieve_and_rank=AsyncMock(return_value={"chunks_for_llm": chunks or []}))
    return agent


async def run(agent, question, session="s1", block_action=None, site="edu-agent-test"):
    events = []
    db = SimpleNamespace(commit=AsyncMock())
    async for e in agent.process_agent_stream(
        db=db, site_id=site, session_id=session, question=question, customer_id=None,
        customer=None, config=None, brand_name="Admizz", block_action=block_action,
    ):
        events.append(e)
    return events


@pytest.fixture(autouse=True)
def _catalog():
    from app.services import education_kb_blocks
    education_kb_blocks._llm_shape_cache.clear()
    education_kb_blocks._shared_cache.clear()
    cat = make_catalog()
    cat.site_id = "edu-agent-test"
    register_catalog(cat)
    register_catalog(Catalog(site_id="edu-empty"))


def types(events):
    return [e["type"] for e in events]


@pytest.mark.asyncio
async def test_core_question_streams_block_then_leadin_without_tools_or_rag():
    agent = make_agent([[_chunk("Here you go!")]])
    events = await run(agent, "I want to study abroad")

    assert types(events) == ["tool_call", "tool_call", "ui_block", "token", "done"]
    block = events[2]["block"]
    assert block["type"] == "choice_cards" and block["data"]["field"] == "countries"
    assert [o["id"] for o in block["data"]["options"]] == ["uk", "au", "ca"]
    assert "tools" not in agent.client.calls[0]           # code acted; LLM only writes the lead-in
    agent.query_service._retrieve_and_rank.assert_not_awaited()
    assert events[-1]["answer"] == "Here you go!"


def _tap(field, selected=None, value=None, action="select"):
    values = {"field": field}
    values.update({"selected": selected} if selected is not None else {"value": value})
    return {"blockId": "b", "blockType": "x", "actionId": action, "values": values, "displayText": "tap"}


@pytest.mark.asyncio
async def test_tap_updates_profile_then_code_shows_the_next_card():
    agent = make_agent([[_chunk("UK and Australia, nice.")]])
    events = await run(agent, "U.K., Australia", block_action=_tap("countries", ["uk", "au"]))

    assert agent.memory.profiles[(None, "s1")]["countries"] == ["au", "uk"]   # applied by code, not parsed by the LLM
    block = next(e["block"] for e in events if e["type"] == "ui_block")
    assert block["type"] == "choice_cards" and block["data"]["field"] == "study_level"   # next slot, enforced in code
    assert "tools" not in agent.client.calls[0]


@pytest.mark.asyncio
async def test_guided_flow_walks_card_slots_in_order_then_hands_text_slots_to_the_llm():
    agent = make_agent([[_chunk("a")], [_chunk("b")], [_chunk("c")], [_chunk("d")]])
    seen = []
    for tap in (_tap("countries", ["uk"]), _tap("study_level", ["master"]),
                _tap("budget", value=30000, action="set_value"), _tap("intake", ["September"])):
        events = await run(agent, "tap", block_action=tap)
        block = next((e["block"] for e in events if e["type"] == "ui_block"), None)
        seen.append(block["data"]["field"] if block else None)

    assert seen == ["study_level", "budget", "intake", None]     # after intake: subject/score are text-only
    assert "tools" in agent.client.calls[3]                       # LLM asks the text question itself
    system = agent.client.calls[3]["messages"][0]["content"]
    assert "field of study via ask in plain text" in system


@pytest.mark.asyncio
async def test_explore_tap_shows_country_facts_deterministically():
    agent = make_agent([[_chunk("Australia in short:")]])
    tap = {"blockId": "b", "blockType": "match_cards", "actionId": "explore",
           "values": {"country": "au"}, "displayText": "Tell me more about Australia"}
    events = await run(agent, "Tell me more about Australia", block_action=tap)
    block = next(e["block"] for e in events if e["type"] == "ui_block")
    assert block["type"] == "info_card" and block["title"] == "Australia quick facts"


@pytest.mark.asyncio
async def test_same_question_in_one_session_streams_the_same_block():
    agent = make_agent([[_chunk("a")], [_chunk("b")], [_chunk("c")]])
    agent.memory.profiles[(None, "s1")] = {"budget": 40000, "english_score": 6.5, "contact": {}, "shown": {}}

    first = next(e["block"] for e in await run(agent, "Which countries fit my profile?") if e["type"] == "ui_block")
    await run(agent, "UK vs Australia?")
    second = next(e["block"] for e in await run(agent, "which countries suit me?") if e["type"] == "ui_block")
    assert first == second and first["type"] == "match_cards"


@pytest.mark.asyncio
async def test_free_form_turn_uses_rag_and_tool_loop_to_save_profile():
    agent = make_agent([
        [_tool_chunk("update_profile", {"english_test": "IELTS", "english_score": 6.5})],
        [_chunk("Noted, thanks!")],
    ])
    events = await run(agent, "my IELTS is 6.5")

    agent.query_service._retrieve_and_rank.assert_awaited_once()
    p = agent.memory.profiles[(None, "s1")]
    assert p["english_score"] == 6.5 and p["english_test"] == "IELTS"
    assert "ui_block" not in types(events)
    assert events[-1]["answer"] == "Noted, thanks!"
    # the tool result went back to the LLM
    assert any(m.get("role") == "tool" and "Saved" in m["content"] for m in agent.client.calls[1]["messages"])


@pytest.mark.asyncio
async def test_no_data_means_no_card_and_tools_stay_available():
    agent = make_agent([[_chunk("What is your budget?")]])
    events = await run(agent, "Which countries fit my profile?")   # empty profile: can't rank honestly

    assert "ui_block" not in types(events)
    assert "tools" in agent.client.calls[0]                         # LLM may follow up (e.g. show_budget_slider)
    assert any("missing" in m["content"] for m in agent.client.calls[0]["messages"] if m["role"] == "system")


@pytest.mark.asyncio
async def test_empty_catalog_tenant_never_gets_a_card():
    agent = make_agent(['{"shape": "none"}', [_chunk("I don't have that detail, but a counselor can help.")]])
    events = await run(agent, "tell me about UK vs Australia", site="edu-empty")
    assert "ui_block" not in types(events)


@pytest.mark.asyncio
async def test_history_records_what_was_shown():
    agent = make_agent([[_chunk("Here you go!")]])
    await run(agent, "I want to study abroad")
    history, titles = await agent.memory.load_history(None, "s1")
    assert titles == ["Which countries are you interested in?"]      # passed to the LLM as a system note...
    assert all("shown" not in m["content"] for m in history)         # ...never as text it could copy into a reply
    stored = agent.memory.messages[(None, "s1")][-1]
    assert stored["blocks"][0]["type"] == "choice_cards"          # blocks kept so a reload can re-render them


@pytest.mark.asyncio
async def test_memory_survives_across_turns_and_agent_instances():
    first = make_agent([[_chunk("Here you go!")], [_chunk("Nice choice.")]])
    await run(first, "I want to study abroad")
    tap = {"blockId": "b", "blockType": "choice_cards", "actionId": "select",
           "values": {"field": "countries", "selected": ["uk"]}, "displayText": "U.K."}
    await run(first, "U.K.", block_action=tap)

    # a different worker/process: fresh agent, same persisted memory
    second = make_agent([[_chunk("Welcome back!")]])
    second.memory = first.memory
    second.memory_for = lambda db: first.memory
    await run(second, "hello again, I have a question about visas")
    system = second.client.calls[0]["messages"][0]["content"]
    assert "Countries: U.K." in system
    roles = [m["role"] for m in second.client.calls[0]["messages"] if m["role"] != "system"]
    assert roles[:2] == ["user", "assistant"]                       # earlier turns were loaded
    notes = [m["content"] for m in second.client.calls[0]["messages"] if m["role"] == "system"]
    assert any("Which countries are you interested in?" in n for n in notes)   # and what the student already saw


@pytest.mark.asyncio
async def test_contact_submit_does_not_link_profile_from_another_device():
    # Product decision 2026-10-13: an unverified email must not pull in another session's profile (privacy). See
    # tests/test_education_email_merge.py for the same rule with production flags.
    agent = make_agent([[_chunk("Thanks, noted.")]])
    agent.memory.profiles[("c", "old-device")] = {
        "countries": ["au"], "budget": 30000, "contact": {"email": "ram@x.com"}, "shown": {}}
    submit = {"blockId": "b", "blockType": "lead_form", "actionId": "submit",
              "values": {"name": "Ram", "email": "Ram@X.com", "phone": "98"}, "displayText": "contact me"}
    async for _ in agent.process_agent_stream(
        db=SimpleNamespace(commit=AsyncMock()), site_id="edu-agent-test", session_id="new-device", question="contact me",
        customer_id="c", customer=None, config=None, brand_name="Admizz", block_action=submit,
    ):
        pass
    new = agent.memory.profiles[("c", "new-device")]
    assert not new.get("countries") and not new.get("budget")              # nothing pulled in from the other session
    assert new["contact"]["email"] == "Ram@X.com"                           # the student's own details are still saved


# ---- welcome, journeys, knowledge-base components ----

PROCESS_JSON = json.dumps({"found": True, "title": "Applying through Admizz", "source_titles": ["Process FAQ"], "steps": [
    {"title": "Book a consultation"}, {"title": "Discuss your options"}, {"title": "Application documents"}, {"title": "Visa support"}]})
PROCESS_CHUNKS = [{"source_title": "Process FAQ", "content": "The process includes booking a consultation, discussing options, "
                   "and receiving assistance with application documents and visa support."}]


def blocks_of(events):
    return [e["block"] for e in events if e["type"] == "ui_block"]


@pytest.mark.asyncio
@pytest.mark.parametrize("greeting", ["hello", "Hi!", "namaste"])
async def test_greeting_opens_an_interactive_welcome_not_plain_text(greeting):
    agent = make_agent([[_chunk("Hi! Where would you like to start?")]])
    events = await run(agent, greeting)
    [block] = blocks_of(events)
    assert block["type"] == "journey_cards"
    assert [t["id"] for t in block["data"]["tiles"]] == ["find", "eligibility", "costs", "apply", "counselor"]
    assert "tools" not in agent.client.calls[0]
    agent.query_service._retrieve_and_rank.assert_not_awaited()


@pytest.mark.asyncio
async def test_welcome_only_offers_what_the_tenant_can_deliver():
    agent = make_agent([[_chunk("Hi!")]])
    [block] = blocks_of(await run(agent, "hello", site="edu-empty"))
    assert [t["id"] for t in block["data"]["tiles"]] == ["apply", "counselor"]   # no country data -> no country tiles


def _start(journey):
    return {"blockId": "w", "blockType": "journey_cards", "actionId": "start", "values": {"journey": journey}, "displayText": journey}


@pytest.mark.asyncio
async def test_costs_journey_asks_which_country_then_shows_the_calculator():
    agent = make_agent([[_chunk("Which country?")], [_chunk("Here you go.")]])
    [pick] = blocks_of(await run(agent, "Estimate my costs", block_action=_start("costs")))
    assert pick["type"] == "choice_cards" and pick["data"]["field"] == "focus_country" and pick["data"]["multi"] is False
    assert agent.memory.profiles[(None, "s1")]["goal"] == "costs"

    [calc] = blocks_of(await run(agent, "Australia", block_action=_tap("focus_country", ["au"])))
    assert calc["type"] == "cost_calculator" and calc["title"] == "Australia cost calculator"
    assert {p["id"]: (p["min"], p["max"]) for p in calc["data"]["parts"]} == {"tuition": (20000, 35000), "living": (18000, 24000)}
    assert "goal" not in agent.memory.profiles[(None, "s1")]
    assert "tools" not in agent.client.calls[1]


@pytest.mark.asyncio
async def test_eligibility_journey_uses_the_known_country_directly():
    agent = make_agent([[_chunk("Let's check.")]])
    agent.memory.profiles[(None, "s1")] = {"countries": ["uk"], "english_score": 7, "contact": {}, "shown": {}}
    [block] = blocks_of(await run(agent, "Check my eligibility", block_action=_start("eligibility")))
    assert block["type"] == "eligibility_meter" and block["title"] == "U.K. eligibility"


@pytest.mark.asyncio
async def test_cost_question_with_a_named_country_shows_the_calculator_and_remembers_the_focus():
    agent = make_agent([[_chunk("Here.")], [_chunk("And now.")]])
    [calc] = blocks_of(await run(agent, "how much does the UK cost"))
    assert calc["type"] == "cost_calculator"
    assert agent.memory.profiles[(None, "s1")]["focus_country"] == "uk"
    # a follow-up with no country now resolves to the one in focus
    [again] = blocks_of(await run(agent, "How much will it cost?"))
    assert again["type"] == "cost_calculator" and again["title"] == "U.K. cost calculator"


@pytest.mark.asyncio
async def test_visa_process_question_becomes_a_stepper_built_from_the_knowledge_base():
    agent = make_agent([PROCESS_JSON, [_chunk("Here is how applying works.")]], chunks=PROCESS_CHUNKS)
    events = await run(agent, "What is the application process?")

    [block] = blocks_of(events)
    assert block["type"] == "stepper" and block["sources"] == ["Process FAQ"]
    assert len(block["data"]["steps"]) == 4
    assert types(events).index("ui_block") < types(events).index("token")
    assert "tools" not in agent.client.calls[1]                      # code built it; the LLM only writes the lead-in
    assert agent.client.calls[0]["temperature"] == 0                 # extraction is deterministic


@pytest.mark.asyncio
async def test_asking_the_process_twice_gives_the_identical_stepper_with_one_extraction():
    agent = make_agent([PROCESS_JSON, [_chunk("a")], [_chunk("b")]], chunks=PROCESS_CHUNKS)
    [first] = blocks_of(await run(agent, "What is the application process?"))
    [second] = blocks_of(await run(agent, "how do I apply?"))
    assert first == second
    assert sum(1 for c in agent.client.calls if c.get("response_format")) == 1   # the second one came from the cache


@pytest.mark.asyncio
async def test_how_to_apply_tile_builds_the_stepper_from_the_knowledge_base():
    agent = make_agent([PROCESS_JSON, [_chunk("Here.")]], chunks=PROCESS_CHUNKS)
    [block] = blocks_of(await run(agent, "How to apply", block_action=_start("apply")))
    assert block["type"] == "stepper"
    query = agent.query_service._retrieve_and_rank.await_args.kwargs["question"]
    assert "process to apply" in query                               # retrieval used the journey's own query, not the tile label


@pytest.mark.asyncio
async def test_documents_question_becomes_a_checklist():
    checklist = json.dumps({"found": True, "title": "Admission requirements", "items": [
        {"label": "application form"}, {"label": "academic transcripts"}, {"label": "standardized test scores"}]})
    chunks = [{"source_title": "Requirements", "content": "You need an application form, academic transcripts and standardized test scores."}]
    agent = make_agent([checklist, [_chunk("Here's what you'll need.")]], chunks=chunks)
    [block] = blocks_of(await run(agent, "What documents do I need?"))
    assert block["type"] == "checklist" and len(block["data"]["items"]) == 3


@pytest.mark.asyncio
async def test_knowledge_base_without_the_answer_falls_back_to_a_text_reply():
    agent = make_agent([json.dumps({"found": False}), [_chunk("I don't have those details; a counselor can help.")]],
                       chunks=PROCESS_CHUNKS)
    events = await run(agent, "What is the application process?")
    assert blocks_of(events) == []
    assert "tools" in agent.client.calls[1]                          # normal LLM turn, offering a counselor card
    assert events[-1]["answer"].startswith("I don't have")


@pytest.mark.asyncio
async def test_single_fact_question_stays_plain_text():
    agent = make_agent(['{"shape": "none"}', [_chunk("The site doesn't say whether it's free.")]], chunks=PROCESS_CHUNKS)
    events = await run(agent, "Is Admizz Education free?")
    assert blocks_of(events) == []


# ---- grounding, loading signal, "okay", answered cards, progress ----

@pytest.mark.asyncio
@pytest.mark.parametrize("ack", ["okay", "ok", "Yes", "sure!", "continue"])
async def test_a_bare_acknowledgement_keeps_the_guided_flow_moving(ack):
    agent = make_agent([[_chunk("Great, next:")]])
    agent.memory.profiles[(None, "s1")] = {"countries": ["uk"], "contact": {}, "shown": {}}
    [block] = blocks_of(await run(agent, ack))
    assert block["type"] == "choice_cards" and block["data"]["field"] == "study_level"   # the next missing card
    assert "tools" not in agent.client.calls[0]


@pytest.mark.asyncio
async def test_acknowledgement_with_nothing_to_continue_goes_to_the_llm():
    agent = make_agent([[_chunk("Anything else I can help with?")]])
    agent.memory.profiles[(None, "s1")] = {"countries": ["uk"], "study_level": "master", "budget": 30000, "intake": "September",
                                           "contact": {}, "shown": {}}
    events = await run(agent, "okay")
    assert blocks_of(events) == [] and "tools" in agent.client.calls[0]


@pytest.mark.asyncio
async def test_when_the_knowledge_base_lacks_the_answer_the_llm_is_told_not_to_fill_the_gap():
    """The screenshot bug: 'what's the visa process' got steps from the model's own general knowledge."""
    agent = make_agent([json.dumps({"found": False}), [_chunk("I don't have the visa steps; a counselor can help.")]],
                       chunks=PROCESS_CHUNKS)
    events = await run(agent, "what's the visa process")
    assert blocks_of(events) == []
    notes = [m["content"] for m in agent.client.calls[1]["messages"] if m["role"] == "system"]
    assert any("does NOT contain a clear answer" in n and "general knowledge" in n for n in notes)
    assert "tools" in agent.client.calls[1]                       # so it can offer the counselor card
    prompt = agent.client.calls[1]["messages"][0]["content"]
    assert "do NOT explain how it generally works" in prompt and "NO STALLING" in prompt


@pytest.mark.asyncio
async def test_widget_is_told_what_is_loading_before_the_slow_part_starts():
    agent = make_agent([PROCESS_JSON, [_chunk("Here's how it works:")]], chunks=PROCESS_CHUNKS)
    events = await run(agent, "What is the application process?")
    order = types(events)
    assert order.index("ui_pending") < order.index("ui_block")
    pending = next(e for e in events if e["type"] == "ui_pending")
    assert pending == {"type": "ui_pending", "block_type": "stepper", "label": "Finding the steps…"}
    # the signal goes out before retrieval, which is the slow part
    assert order[0] == "ui_pending"


@pytest.mark.asyncio
async def test_catalog_cards_need_no_loading_signal():
    agent = make_agent([[_chunk("Hi!")]])
    assert "ui_pending" not in types(await run(agent, "hello"))


@pytest.mark.asyncio
async def test_a_tap_marks_the_block_answered_so_it_reloads_collapsed():
    agent = make_agent([[_chunk("Great.")], [_chunk("And your level?")]])
    first = await run(agent, "I want to study abroad")
    block_id = blocks_of(first)[0]["block_id"]
    tap = {"blockId": block_id, "blockType": "choice_cards", "actionId": "select",
           "values": {"field": "countries", "selected": ["uk"]}, "displayText": "U.K."}
    await run(agent, "U.K.", block_action=tap)

    stored = agent.memory.messages[(None, "s1")][1]            # the assistant message that held the card
    assert stored["blocks"][0]["answered"] == {"field": "countries", "selected": ["uk"]}


@pytest.mark.asyncio
async def test_exploring_a_card_does_not_mark_it_answered():
    agent = make_agent([[_chunk("a")], [_chunk("b")]])
    agent.memory.profiles[(None, "s1")] = {"budget": 40000, "english_score": 6.5, "contact": {}, "shown": {}}
    events = await run(agent, "Which countries fit my profile?")
    block_id = blocks_of(events)[0]["block_id"]
    tap = {"blockId": block_id, "blockType": "match_cards", "actionId": "explore", "values": {"country": "au"}, "displayText": "x"}
    await run(agent, "x", block_action=tap)
    assert agent.memory.messages[(None, "s1")][1]["blocks"][0]["answered"] is None


@pytest.mark.asyncio
async def test_done_reports_profile_progress():
    agent = make_agent([[_chunk("Great.")]])
    agent.memory.profiles[(None, "s1")] = {"countries": ["uk"], "budget": 30000, "contact": {}, "shown": {}}
    done = (await run(agent, "U.K.", block_action=_tap("study_level", ["master"])))[-1]
    assert done["profile_progress"] == {"filled": 3, "total": 6}
