"""
ZUNKIREE-FAST-FACTS-BRIEF: quick-facts fast-path in clinic_tools._search_knowledge.

- A matching question is answered directly — no embeddings call, no
  Pinecone round trip, get_query_service() is never even imported.
- A non-matching question falls through to the existing RAG path unchanged.
- Hours prefer a live, populated ClinicMD branch over the stored fact, so
  the two copies can never drift (S4-TENANT-CONFIG-BRIEF finding #3).
- Facts are cached per tenant (site_id) — a second lookup doesn't re-hit the DB.
"""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.customer import Customer
from app.services import clinic_tools


def _make_customer() -> Customer:
    return Customer(
        id=uuid.UUID("00000000-0000-0000-0000-0000000000aa"),
        name="The Dental City",
        site_id="dental-city",
        api_key="test-key",
    )


def _fake_db(rows: list[SimpleNamespace]) -> AsyncMock:
    db = AsyncMock()
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))
    db.execute = AsyncMock(return_value=result)
    return db


def _fact_row(category: str, keywords: list[str], answer: str) -> SimpleNamespace:
    return SimpleNamespace(category=category, keywords=keywords, answer=answer)


@pytest.fixture(autouse=True)
def _reset():
    clinic_tools.reset_org_cache()
    clinic_tools.reset_quick_facts_cache()
    yield
    clinic_tools.reset_org_cache()
    clinic_tools.reset_quick_facts_cache()


@pytest.mark.asyncio
async def test_quick_fact_hit_never_touches_rag(monkeypatch):
    """A matching question is answered from the quick-facts row and the RAG
    module is never imported/called — the actual latency win this brief is for."""
    rows = [_fact_row("hours", ["hour", "open", "close"], "Dental City is open every day, 10:00 AM to 8:00 PM.")]
    db = _fake_db(rows)
    customer = _make_customer()

    called = {"rag": False}

    class ExplodingQueryService:
        async def _retrieve_and_rank(self, *a, **kw):
            called["rag"] = True
            raise AssertionError("RAG path must not run on a quick-facts hit")

    monkeypatch.setattr(clinic_tools, "get_clinicmd_client", lambda: None)
    import app.services.query as query_module
    monkeypatch.setattr(query_module, "get_query_service", lambda: ExplodingQueryService())

    result = await clinic_tools._search_knowledge(db, customer, config=None, site_id="dental-city", query="What time do you open?")

    assert called["rag"] is False
    assert result["chunks"] == [{"content": "Dental City is open every day, 10:00 AM to 8:00 PM."}]


@pytest.mark.asyncio
async def test_no_match_falls_through_to_rag_unchanged(monkeypatch):
    rows = [_fact_row("hours", ["hour", "open", "close"], "Dental City is open every day, 10:00 AM to 8:00 PM.")]
    db = _fake_db(rows)
    customer = _make_customer()

    class FakeQueryService:
        async def _retrieve_and_rank(self, db, customer, config, site_id, query):
            return {"chunks_for_llm": [{"content": "Parking is available behind the building."}]}

    import app.services.query as query_module
    monkeypatch.setattr(query_module, "get_query_service", lambda: FakeQueryService())

    result = await clinic_tools._search_knowledge(db, customer, config=None, site_id="dental-city", query="Is there parking?")

    assert result["chunks"] == [{"content": "Parking is available behind the building."}]


@pytest.mark.asyncio
async def test_empty_facts_falls_through_to_rag(monkeypatch):
    db = _fake_db([])
    customer = _make_customer()

    class FakeQueryService:
        async def _retrieve_and_rank(self, db, customer, config, site_id, query):
            return {"chunks_for_llm": [{"content": "some kb content"}]}

    import app.services.query as query_module
    monkeypatch.setattr(query_module, "get_query_service", lambda: FakeQueryService())

    result = await clinic_tools._search_knowledge(db, customer, config=None, site_id="dental-city", query="anything")
    assert result["chunks"] == [{"content": "some kb content"}]


@pytest.mark.asyncio
async def test_hours_prefers_live_clinicmd_branch_when_populated():
    """S4 finding #3: if ClinicMD already has real hours for this tenant's
    branch, don't answer from the (possibly stale) stored quick fact."""
    rows = [_fact_row("hours", ["hour", "open", "close"], "STALE: open 9 to 5.")]
    db = _fake_db(rows)
    customer = _make_customer()

    clinic_tools._cache_set(clinic_tools._ORG_CACHE, "dental-city", {
        "org_id": "org-1",
        "branches": [{"id": "b1", "name": "Main Branch", "open_time": "10:00", "close_time": "20:00", "timezone": "Asia/Kathmandu"}],
    })

    result = await clinic_tools._search_knowledge(db, customer, config=None, site_id="dental-city", query="What are your hours?")

    assert result["chunks"] == [{"content": "Main Branch is open 10:00 to 20:00 (Asia/Kathmandu)."}]


@pytest.mark.asyncio
async def test_hours_uses_stored_fact_when_clinicmd_branch_not_populated():
    rows = [_fact_row("hours", ["hour", "open", "close"], "Dental City is open every day, 10:00 AM to 8:00 PM.")]
    db = _fake_db(rows)
    customer = _make_customer()

    clinic_tools._cache_set(clinic_tools._ORG_CACHE, "dental-city", {
        "org_id": "org-1",
        "branches": [{"id": "b1", "name": "Main Branch", "open_time": None, "close_time": None, "timezone": "Asia/Kathmandu"}],
    })

    result = await clinic_tools._search_knowledge(db, customer, config=None, site_id="dental-city", query="What are your hours?")

    assert result["chunks"] == [{"content": "Dental City is open every day, 10:00 AM to 8:00 PM."}]


@pytest.mark.asyncio
async def test_facts_cached_per_tenant_no_repeat_db_hit():
    rows = [_fact_row("address", ["located", "address"], "Dental City is located in Thimi, Bhaktapur, Nepal.")]
    db = _fake_db(rows)
    customer = _make_customer()

    await clinic_tools._quick_fact_lookup(db, customer, "Where are you located?")
    await clinic_tools._quick_fact_lookup(db, customer, "What's your address?")

    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_quick_facts_cache_reloads_after_ttl_expiry(monkeypatch):
    """S53-CACHE-EXPIRY-BRIEF: an entry older than the 60s TTL reloads from
    the DB on the next lookup, instead of serving stale facts forever."""
    rows = [_fact_row("address", ["located", "address"], "Dental City is located in Thimi, Bhaktapur, Nepal.")]
    db = _fake_db(rows)
    customer = _make_customer()

    await clinic_tools._quick_fact_lookup(db, customer, "Where are you located?")
    assert db.execute.await_count == 1

    # Age the cached entry past the TTL without waiting real time.
    facts, _cached_at = clinic_tools._QUICK_FACTS_CACHE["dental-city"]
    stale_at = clinic_tools._time.monotonic() - clinic_tools._QUICK_FACTS_CACHE_TTL_SECONDS - 1
    clinic_tools._QUICK_FACTS_CACHE["dental-city"] = (facts, stale_at)

    await clinic_tools._quick_fact_lookup(db, customer, "What's your address?")
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_quick_facts_cache_reuses_entry_within_ttl():
    """A fresh (within-TTL) entry is served from cache, not reloaded."""
    rows = [_fact_row("address", ["located", "address"], "Dental City is located in Thimi, Bhaktapur, Nepal.")]
    db = _fake_db(rows)
    customer = _make_customer()

    await clinic_tools._quick_fact_lookup(db, customer, "Where are you located?")
    assert db.execute.await_count == 1

    await clinic_tools._quick_fact_lookup(db, customer, "What's your address?")
    assert db.execute.await_count == 1


@pytest.mark.asyncio
async def test_org_cache_reloads_after_ttl_expiry(monkeypatch):
    """Same treatment for _ORG_CACHE, at its own (longer) TTL."""
    customer = _make_customer()
    call_count = {"n": 0}

    class FakeClient:
        async def get_org(self, remote_site_id):
            call_count["n"] += 1
            return {"id": f"org-{call_count['n']}"}

        async def list_branches(self, org_id):
            return [{"id": "b1", "name": "Main Branch"}]

    creds_row = SimpleNamespace(remote_site_id="remote-1")
    db = AsyncMock()
    result = SimpleNamespace(scalar_one_or_none=lambda: creds_row)
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()

    monkeypatch.setattr(clinic_tools, "get_clinicmd_client", lambda: FakeClient())

    org_id, _branches = await clinic_tools._resolve_org(db, customer)
    assert org_id == "org-1"
    assert call_count["n"] == 1

    cached, cached_at = clinic_tools._ORG_CACHE["dental-city"]
    stale_at = clinic_tools._time.monotonic() - clinic_tools._ORG_CACHE_TTL_SECONDS - 1
    clinic_tools._ORG_CACHE["dental-city"] = (cached, stale_at)

    org_id, _branches = await clinic_tools._resolve_org(db, customer)
    assert org_id == "org-2"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_org_cache_reuses_entry_within_ttl(monkeypatch):
    customer = _make_customer()
    call_count = {"n": 0}

    class FakeClient:
        async def get_org(self, remote_site_id):
            call_count["n"] += 1
            return {"id": f"org-{call_count['n']}"}

        async def list_branches(self, org_id):
            return [{"id": "b1", "name": "Main Branch"}]

    creds_row = SimpleNamespace(remote_site_id="remote-1")
    db = AsyncMock()
    result = SimpleNamespace(scalar_one_or_none=lambda: creds_row)
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()

    monkeypatch.setattr(clinic_tools, "get_clinicmd_client", lambda: FakeClient())

    await clinic_tools._resolve_org(db, customer)
    org_id, _branches = await clinic_tools._resolve_org(db, customer)

    assert org_id == "org-1"
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_no_query_returns_empty_without_db_hit():
    db = _fake_db([])
    customer = _make_customer()
    result = await clinic_tools._search_knowledge(db, customer, config=None, site_id="dental-city", query="")
    assert result == {"chunks": []}
    db.execute.assert_not_awaited()


# --- ZUNKIREE-FAST-FACTS-NEPALI-BRIEF: Devanagari keywords ---
# The matching mechanism is a plain substring check, already language-agnostic
# with zero code change — these just prove the Nepali keyword content works
# the same way the English keywords already did.

@pytest.mark.asyncio
async def test_nepali_keyword_matches_hours_fact(monkeypatch):
    rows = [_fact_row("hours", ["hour", "open", "खुल्ने", "खुल्छ", "समय"], "Dental City is open every day, 10:00 AM to 8:00 PM.")]
    db = _fake_db(rows)
    customer = _make_customer()

    result = await clinic_tools._search_knowledge(db, customer, config=None, site_id="dental-city", query="तपाईंको खुल्ने समय कति हो?")

    assert result["chunks"] == [{"content": "Dental City is open every day, 10:00 AM to 8:00 PM."}]


@pytest.mark.asyncio
async def test_nepali_keyword_matches_address_fact():
    rows = [_fact_row("address", ["located", "address", "ठेगाना", "कहाँ"], "Dental City is located in Thimi, Bhaktapur, Nepal.")]
    db = _fake_db(rows)
    customer = _make_customer()

    result = await clinic_tools._quick_fact_lookup(db, customer, "क्लिनिकको ठेगाना के हो?")

    assert result == {"category": "address", "keywords": rows[0].keywords, "answer": "Dental City is located in Thimi, Bhaktapur, Nepal."}


@pytest.mark.asyncio
async def test_nepali_and_english_keywords_coexist_on_same_fact():
    """Adding Nepali variants must not disturb the English matches PR #77 already proved."""
    rows = [_fact_row("hours", ["hour", "hours", "open", "खुल्ने", "समय"], "Dental City is open every day, 10:00 AM to 8:00 PM.")]
    db = _fake_db(rows)
    customer = _make_customer()

    en_result = await clinic_tools._quick_fact_lookup(db, customer, "What time do you open?")
    clinic_tools.reset_quick_facts_cache()
    ne_result = await clinic_tools._quick_fact_lookup(_fake_db(rows), customer, "खुल्ने समय के हो?")

    assert en_result["answer"] == ne_result["answer"] == "Dental City is open every day, 10:00 AM to 8:00 PM."


@pytest.mark.asyncio
async def test_devanagari_query_with_no_keyword_match_falls_through():
    rows = [_fact_row("hours", ["hour", "open", "खुल्ने"], "Dental City is open every day, 10:00 AM to 8:00 PM.")]
    db = _fake_db(rows)
    customer = _make_customer()

    # "पार्किङ" (parking) isn't covered by any fact/keyword.
    result = await clinic_tools._quick_fact_lookup(db, customer, "पार्किङ छ कि छैन?")

    assert result is None
