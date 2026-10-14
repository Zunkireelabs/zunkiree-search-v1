"""Golden snapshot of every education UI block, built from fixed inputs.

Pins the exact emitted JSON (type, data, block_id, schema_version, fallback_text, actions, ...) so a refactor of
the registry/schema layer can be proven output-neutral. If a block legitimately changes, regenerate with
    UPDATE_GOLDEN=1 pytest tests/test_education_block_golden.py
and review the golden-file diff like any other change."""
import asyncio
import json
import os
from pathlib import Path

import pytest

from app.schemas.ui_blocks import build_block
from app.services.education_kb_blocks import SHAPES, extract_block
from app.services.education_profile import apply_updates, new_profile
from app.services.education_tools import execute_education_tool
from tests.test_education_consistency import make_catalog
from tests.test_education_kb_blocks import FakeClient, j

GOLDEN = Path(__file__).parent / "golden" / "education_blocks.json"

CHUNKS = [
    {"source_title": "Process FAQ", "content": "The process includes booking a consultation, discussing options, and receiving "
     "assistance with application documents and visa support."},
    {"source_title": "Requirements", "content": "Admission requirements: complete an application form, submit academic transcripts, "
     "and provide standardized test scores. Applications open in January and close in March. Offers are sent in April."},
    {"source_title": "Services", "content": "We offer counselling sessions, scholarship guidance and visa support for students."},
]

KB_REPLIES = {
    "process": j(found=True, title="applying through us", source_titles=["Process FAQ"], steps=[
        {"title": "Book a consultation", "detail": "Start with a consultation."}, {"title": "Discuss your options"},
        {"title": "Application documents"}, {"title": "Visa support"}]),
    "checklist": j(found=True, title="admission documents", source_titles=["Requirements"], items=[
        {"label": "application form"}, {"label": "Academic transcripts", "note": "official copies"}, {"label": "test scores"}]),
    "timeline": j(found=True, title="key dates", source_titles=["Requirements"], events=[
        {"when": "January", "title": "Applications open"}, {"when": "March", "title": "Applications close"},
        {"when": "April", "title": "Offers are sent"}]),
    "offerings": j(found=True, title="what we offer", source_titles=["Services"], items=[
        {"title": "Counselling sessions", "summary": "one to one", "detail": "We offer counselling sessions."},
        {"title": "Scholarship guidance", "summary": "funding help", "detail": "Scholarship guidance for students."}]),
}

TOOL_CASES = [
    ("welcome", "show_welcome", {}),
    ("choice_countries", "show_choice", {"kind": "countries"}),
    ("choice_study_level", "show_choice", {"kind": "study_level"}),
    ("choice_intake", "show_choice", {"kind": "intake"}),
    ("choice_country_one", "show_choice", {"kind": "country_one"}),
    ("budget", "show_budget_slider", {}),
    ("matches", "show_country_matches", {}),
    ("facts_uk", "show_country_facts", {"country": "uk"}),
    ("compare_uk_au", "compare_countries", {"countries": ["uk", "au"]}),
    ("eligibility_uk", "check_eligibility", {"country": "uk"}),
    ("cost_au", "show_cost_calculator", {"country": "au"}),
    ("profile", "show_profile", {}),
    ("lead_form", "show_lead_form", {}),
]


def _profile() -> dict:
    p = new_profile()
    apply_updates(p, {"countries": ["uk", "au"], "study_level": "master", "field_of_study": "Business", "intake": "September",
                      "budget": 40000, "english_test": "IELTS", "english_score": 6.5, "academic_score": 70})
    return p


def _build_all() -> dict:
    catalog = make_catalog()
    out: dict[str, dict] = {}
    for name, tool, args in TOOL_CASES:
        outcome = execute_education_tool(tool, dict(args), _profile(), catalog)
        assert outcome.block is not None, f"{name} produced no block"
        out[name] = outcome.block.model_dump()
    for shape in SHAPES:
        block = asyncio.run(extract_block(FakeClient([KB_REPLIES[shape]]), "m", shape, "q", CHUNKS))
        assert block is not None, f"kb shape {shape} produced no block"
        out[f"kb_{shape}"] = block.model_dump()
    # No backend tool emits quick_chips today; keep its schema pinned anyway.
    out["quick_chips"] = build_block("quick_chips", {"chips": [{"id": "a", "label": "Chip A"}]},
                                     fallback_text="Chip A").model_dump()
    return json.loads(json.dumps(out, sort_keys=True, default=str))


def test_every_block_type_is_covered_by_the_golden_set():
    from app.schemas.ui_blocks import DATA_MODELS
    assert {b["type"] for b in _build_all().values()} == set(DATA_MODELS)


def test_blocks_match_the_golden_file():
    built = _build_all()
    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(built, indent=2, sort_keys=True) + "\n")
        pytest.skip("golden file regenerated")
    golden = json.loads(GOLDEN.read_text())
    assert built.keys() == golden.keys()
    for name in golden:
        assert built[name] == golden[name], f"block '{name}' no longer matches its golden snapshot"


def test_building_twice_is_identical():
    assert _build_all() == _build_all()
