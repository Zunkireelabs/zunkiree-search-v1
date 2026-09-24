"""
Generic tenant_quick_facts writer that replaces the dental-city-only
seed_dental_city_quick_facts.py, per the platform brief's ask to onboard a
new clinic (Healthy Smile) as data only, no code change.
"""
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.seed_tenant_quick_facts import VALID_CATEGORIES, _load_facts, seed
from app.models.customer import Customer


def _write(tmp_path: Path, data) -> Path:
    p = tmp_path / "facts.json"
    p.write_text(json.dumps(data))
    return p


# ---------- _load_facts validation ----------


def test_load_facts_accepts_valid_shape(tmp_path):
    path = _write(tmp_path, [
        {"category": "hours", "keywords": ["hour", "खुल्ने"], "answer": "Open 10-8."},
    ])
    facts = _load_facts(path)
    assert facts[0]["category"] == "hours"


def test_load_facts_rejects_missing_file(tmp_path):
    with pytest.raises(SystemExit, match="No such file"):
        _load_facts(tmp_path / "missing.json")


def test_load_facts_rejects_invalid_json(tmp_path):
    path = tmp_path / "facts.json"
    path.write_text("{not json")
    with pytest.raises(SystemExit, match="Invalid JSON"):
        _load_facts(path)


def test_load_facts_rejects_non_list(tmp_path):
    path = _write(tmp_path, {"category": "hours", "keywords": [], "answer": "x"})
    with pytest.raises(SystemExit, match="non-empty JSON array"):
        _load_facts(path)


def test_load_facts_rejects_empty_list(tmp_path):
    path = _write(tmp_path, [])
    with pytest.raises(SystemExit, match="non-empty JSON array"):
        _load_facts(path)


def test_load_facts_rejects_missing_required_field(tmp_path):
    path = _write(tmp_path, [{"category": "hours", "keywords": []}])  # no answer
    with pytest.raises(SystemExit, match="missing required field"):
        _load_facts(path)


def test_load_facts_rejects_invalid_category(tmp_path):
    path = _write(tmp_path, [{"category": "pricing", "keywords": [], "answer": "x"}])
    with pytest.raises(SystemExit, match="pricing"):
        _load_facts(path)


def test_load_facts_rejects_non_string_keywords(tmp_path):
    path = _write(tmp_path, [{"category": "hours", "keywords": [1, 2], "answer": "x"}])
    with pytest.raises(SystemExit, match="keywords must be a list of strings"):
        _load_facts(path)


def test_load_facts_rejects_blank_answer(tmp_path):
    path = _write(tmp_path, [{"category": "hours", "keywords": ["hour"], "answer": "  "}])
    with pytest.raises(SystemExit, match="answer must be a non-empty string"):
        _load_facts(path)


def test_valid_categories_matches_model_comment():
    # tenant_quick_fact.py's category column comment lists these seven.
    assert VALID_CATEGORIES == {
        "hours", "address", "contact", "staff", "services_overview", "policy", "other",
    }


# ---------- shipped dental-city data file still loads ----------


def test_dental_city_data_file_is_valid():
    path = Path(__file__).parent.parent / "scripts" / "seed_data" / "dental_city_quick_facts.json"
    facts = _load_facts(path)
    assert len(facts) == 6
    assert {f["category"] for f in facts} <= VALID_CATEGORIES


# ---------- seed(): unknown site_id raises, known site_id writes ----------


@pytest.mark.asyncio
async def test_seed_raises_for_unknown_site_id(monkeypatch):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    class _FakeSessionMaker:
        def __call__(self):
            return self
        async def __aenter__(self):
            return db
        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("scripts.seed_tenant_quick_facts.async_session_maker", _FakeSessionMaker())

    with pytest.raises(SystemExit, match="No customer found"):
        await seed("no-such-tenant", [{"category": "hours", "keywords": [], "answer": "x"}])


@pytest.mark.asyncio
async def test_seed_deletes_then_inserts_for_known_site_id(monkeypatch):
    customer = Customer(id=uuid.uuid4(), name="Healthy Smile", site_id="healthy-smile",
                         api_key="key", website_type="clinic")
    db = AsyncMock()
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    db.execute = AsyncMock(return_value=customer_result)
    db.commit = AsyncMock()
    added = []
    db.add = MagicMock(side_effect=added.append)

    class _FakeSessionMaker:
        def __call__(self):
            return self
        async def __aenter__(self):
            return db
        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("scripts.seed_tenant_quick_facts.async_session_maker", _FakeSessionMaker())

    facts = [{"category": "hours", "keywords": ["hour"], "answer": "9-5 daily."}]
    count = await seed("healthy-smile", facts)

    assert count == 1
    db.execute.assert_awaited()  # select + delete both go through db.execute
    assert len(added) == 1
    assert added[0].customer_id == customer.id
    assert added[0].answer == "9-5 daily."
    db.commit.assert_awaited_once()
