"""Interactive answers built from knowledge-base text: fixed shape -> component map,
grounded extraction (no invented items), and the same content -> the same block."""
import json
from types import SimpleNamespace

import pytest

from app.services import education_kb_blocks as kb
from app.services.education_kb_blocks import (
    SHAPE_TO_BLOCK, classify_shape, classify_shape_rules, extract_block, kb_block, looks_like_question,
)

CHUNKS = [
    {"source_title": "Process FAQ", "content": "Q: What is the process to apply? A: The process includes booking a consultation, "
     "discussing options, and receiving assistance with application documents and visa support."},
    {"source_title": "Requirements", "content": "Admission requirements: complete an application form, submit academic transcripts, "
     "and provide standardized test scores. Some programs require essays or letters of recommendation."},
]


class FakeClient:
    """Non-streaming chat.completions: each call pops the next scripted reply (a str)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])


@pytest.fixture(autouse=True)
def _clear_cache():
    kb._llm_shape_cache.clear()
    kb._shared_cache.clear()


def j(**kw):
    return json.dumps(kw)


# ---- shape detection ----

@pytest.mark.parametrize("q,shape", [
    ("What is the visa process?", "process"),
    ("how do I apply", "process"),
    ("what are the steps to study in Canada", "process"),
    ("What documents do I need?", "checklist"),
    ("what are the admission requirements", "checklist"),
    ("what are the deadlines", "timeline"),
    ("how long does admission take", "timeline"),
    ("What services does Admizz offer?", "offerings"),
    ("do you help with scholarships", "offerings"),
    ("What is Admizz Education?", "offerings"),
])
def test_rules_map_questions_to_one_shape(q, shape):
    assert classify_shape_rules(q) == shape


def test_shape_to_component_map_is_fixed():
    assert SHAPE_TO_BLOCK == {"process": "stepper", "checklist": "checklist", "timeline": "timeline", "offerings": "accordion"}


def test_single_facts_and_statements_have_no_shape():
    assert classify_shape_rules("Is Admizz free?") is None
    assert not looks_like_question("my IELTS is 6.5")
    assert looks_like_question("Is Admizz free?")


@pytest.mark.asyncio
async def test_llm_fallback_only_for_unusual_questions_and_is_cached():
    client = FakeClient([j(shape="checklist")])
    assert await classify_shape(client, "m", "What should I get ready before applying abroad?") == "checklist"
    assert await classify_shape(client, "m", "What should I get ready before applying abroad?") == "checklist"
    assert len(client.calls) == 1 and client.calls[0]["temperature"] == 0

    quiet = FakeClient([])
    assert await classify_shape(quiet, "m", "my IELTS is 6.5") is None        # a statement: no call at all
    assert await classify_shape(quiet, "m", "How do I apply") == "process"    # a rule hit: no call at all
    assert quiet.calls == []


@pytest.mark.asyncio
async def test_llm_fallback_failures_and_junk_degrade_to_no_shape():
    assert await classify_shape(FakeClient([j(shape="banana")]), "m", "Is it really worth the money to go?") is None
    assert await classify_shape(FakeClient([RuntimeError("down")]), "m", "Is it really worth it to study abroad?") is None


# ---- grounded extraction ----

GOOD_STEPS = j(found=True, title="Applying through Admizz", source_titles=["Process FAQ"], steps=[
    {"title": "Book a consultation", "detail": "Start with a consultation."},
    {"title": "Discuss your options", "detail": None},
    {"title": "Application documents", "detail": "Get help with application documents."},
    {"title": "Visa support"}])


@pytest.mark.asyncio
async def test_extracts_a_stepper_with_sources():
    client = FakeClient([GOOD_STEPS])
    block = await extract_block(client, "m", "process", "What is the process?", CHUNKS)
    assert block.type == "stepper" and block.title == "Applying through Admizz"
    assert [s["title"] for s in block.data["steps"]][:2] == ["Book a consultation", "Discuss your options"]
    assert block.sources == ["Process FAQ"]
    assert client.calls[0]["temperature"] == 0
    assert "ONLY information stated in the KNOWLEDGE BASE" in client.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_invented_items_are_dropped_and_too_few_means_no_component():
    invented = j(found=True, title="Process", steps=[
        {"title": "Book a consultation"},
        {"title": "Pay a 5000 dollar deposit to Zorblax Quantum Holdings"},     # nothing like it in the text
        {"title": "Visa support"}])
    block = await extract_block(FakeClient([invented]), "m", "process", "q", CHUNKS)
    assert [s["title"] for s in block.data["steps"]] == ["Book a consultation", "Visa support"]

    mostly_invented = j(found=True, title="Process", steps=[{"title": "Book a consultation"}, {"title": "Zorblax Quantum"}])
    assert await extract_block(FakeClient([mostly_invented]), "m", "process", "q", CHUNKS) is None   # only 1 left, needs 2


@pytest.mark.asyncio
async def test_not_found_bad_json_errors_and_no_chunks_all_mean_no_component():
    assert await extract_block(FakeClient([j(found=False)]), "m", "process", "q", CHUNKS) is None
    assert await extract_block(FakeClient(["not json"]), "m", "process", "q", CHUNKS) is None
    assert await extract_block(FakeClient([RuntimeError("down")]), "m", "process", "q", CHUNKS) is None
    never = FakeClient([])
    assert await extract_block(never, "m", "process", "q", []) is None and never.calls == []


@pytest.mark.asyncio
async def test_checklist_and_offerings_and_timeline_build_their_own_components():
    checklist = j(found=True, title="Admission requirements", items=[
        {"label": "Application form"}, {"label": "Academic transcripts"}, {"label": "Standardized test scores"},
        {"label": "Essays or letters of recommendation", "note": "Only some programs"}])
    b = await extract_block(FakeClient([checklist]), "m", "checklist", "q", CHUNKS)
    assert b.type == "checklist" and len(b.data["items"]) == 4

    offerings = j(found=True, title="Services", items=[
        {"title": "Visa support", "summary": "Student visa help", "detail": "Receiving assistance with visa support."}])
    assert (await extract_block(FakeClient([offerings]), "m", "offerings", "q", CHUNKS)).type == "accordion"

    timeline = j(found=True, title="Dates", events=[{"when": "Sep", "title": "consultation"}, {"when": "Jan", "title": "options"}])
    chunks = CHUNKS + [{"source_title": "Dates", "content": "Sep Jan consultation options"}]
    assert (await extract_block(FakeClient([timeline]), "m", "timeline", "q", chunks)).type == "timeline"


@pytest.mark.asyncio
async def test_unknown_sources_fall_back_to_the_top_page():
    reply = j(found=True, title="P", source_titles=["Made Up Page"], steps=[{"title": "Book a consultation"}, {"title": "Visa support"}])
    block = await extract_block(FakeClient([reply]), "m", "process", "q", CHUNKS)
    assert block.sources == ["Process FAQ"]


# ---- same content -> same block ----

@pytest.mark.asyncio
async def test_same_content_reuses_the_identical_block_without_another_llm_call():
    client, profile = FakeClient([GOOD_STEPS]), {"shown": {}}
    first = await kb_block(client, "m", profile, "process", "What is the process?", CHUNKS)
    second = await kb_block(client, "m", profile, "process", "How do I apply, step by step?", CHUNKS)   # different wording
    assert first == second and len(client.calls) == 1


@pytest.mark.asyncio
async def test_rewording_that_retrieves_different_supporting_passages_still_gets_the_same_block():
    """The bug found with the real model: 'How to apply' vs 'What is the application process?' retrieve the same
    best passage but different supporting ones, and used to produce different components (or none)."""
    extra_a = {"source_title": "Visa FAQ", "content": "Admizz offers comprehensive visa guidance."}
    extra_b = {"source_title": "Contact", "content": "Contact Admizz support by email."}
    client, profile = FakeClient([GOOD_STEPS]), {"shown": {}}
    first = await kb_block(client, "m", profile, "process", "How to apply", [CHUNKS[0], extra_a])
    second = await kb_block(client, "m", profile, "process", "What is the application process?", [CHUNKS[0], extra_b])
    assert first == second and len(client.calls) == 1


@pytest.mark.asyncio
async def test_a_different_best_passage_or_shape_is_built_fresh():
    client, profile = FakeClient([GOOD_STEPS, GOOD_STEPS, GOOD_STEPS]), {"shown": {}}
    await kb_block(client, "m", profile, "process", "q", CHUNKS)
    await kb_block(client, "m", profile, "process", "q", CHUNKS[1:])      # best passage differs
    await kb_block(client, "m", {"shown": {}}, "offerings", "q", CHUNKS)  # shape differs
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_students_share_the_extraction_and_get_the_identical_block():
    client = FakeClient([GOOD_STEPS])
    a = await kb_block(client, "m", {"shown": {}}, "process", "q", CHUNKS)
    b = await kb_block(client, "m", {"shown": {}}, "process", "q", CHUNKS)   # a different student
    assert a == b and len(client.calls) == 1


@pytest.mark.asyncio
async def test_titles_are_capitalised():
    reply = j(found=True, title="admission documents", items=[{"label": "application form"}, {"label": "academic transcripts"}])
    block = await extract_block(FakeClient([reply]), "m", "checklist", "q", CHUNKS)
    assert block.title == "Admission documents"


@pytest.mark.asyncio
async def test_item_labels_are_capitalised_like_titles():
    reply = j(found=True, title="Admission documents", items=[{"label": "application form"}, {"label": "academic transcripts", "note": "required"}])
    block = await extract_block(FakeClient([reply]), "m", "checklist", "q", CHUNKS)
    assert [i["label"] for i in block.data["items"]] == ["Application form", "Academic transcripts"]
    assert block.data["items"][1]["note"] == "required"          # notes keep the knowledge base's own wording
