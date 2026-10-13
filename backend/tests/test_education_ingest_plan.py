"""What a safe ingestion of the Admizz pages would do, proved against fakes only: no database, vector store, embeddings or network.
The pure module decides overlap, classes, cost, ordering and recovery; a store interface (faked here) does the writing in a
future, separately approved task. A second group of tests pins down how the EXISTING ingestion service really behaves
(append-only, Postgres committed before Pinecone), with fake clients."""
import uuid
from types import SimpleNamespace

import pytest

from app.services.education_ingest_plan import (
    AddResult, ExistingSource, PageWriteError, Plan, PlanPage, classify_content, estimate_embeddings, execute_plan, find_inconsistent_jobs,
    find_overlap, plan_ingestion, preflight,
)

HOST = "https://admizzeducation.com"


def _existing(job, title, url=None, chars=650, tokens=140, chunks=1):
    return ExistingSource(job_id=job, source_type="text", source_url=url, title=title, chunks=chunks, characters=chars, tokens=tokens)


def _page(pid="uk-guide", url=f"{HOST}/study-in-the-uk", title="Study in the UK - Admizz Education", chunks=6, tokens=2400, **kw):
    return PlanPage(id=pid, canonical_url=url, title=title, chunks=chunks, tokens=tokens, **kw)


# --- content classes: never "verified" ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("kw,expected", [
    (dict(has_checked_statement=True, references=[{"url": "https://www.gov.uk/student-visa"}]), "source_backed"),
    (dict(has_checked_statement=True, references=[{"url": "https://www.canada.ca/en/x.html"}]), "source_backed"),
    (dict(has_checked_statement=True, references=[]), "dated"),
    (dict(has_checked_statement=True, references=[{"url": "https://blog.example.com/x"}]), "dated"),
    (dict(published="2026-10-05", references=[]), "dated"),
    (dict(checked="2026-10", references=[]), "dated"),
    (dict(references=[{"url": "https://www.gov.uk/x"}]), "explanatory"),         # a reference alone, with no date, is not enough
    (dict(), "explanatory"),
])
def test_content_class(kw, expected):
    assert classify_content(**kw) == expected


def test_no_content_class_is_called_verified():
    values = {classify_content(has_checked_statement=c, references=r) for c in (True, False) for r in ([], [{"url": "https://www.gov.uk/x"}])}
    assert "verified" not in values and all("verif" not in v for v in values)


# --- overlap with what is already in the knowledge base ----------------------------------------------------------------------------

def test_a_matching_url_is_the_only_proof_of_the_same_source():
    existing = [_existing("j1", "Anything", url=f"{HOST}/study-in-the-uk")]
    hit = find_overlap(f"{HOST}/study-in-the-uk", "Study in the UK - Admizz Education", existing)
    assert hit["match"] == "url" and hit["job_id"] == "j1" and hit["proof"] == "same_url"


def test_a_matching_title_is_reported_as_a_title_only_match_never_as_the_same_source():
    existing = [_existing("j2", "Study in the UK - Admizz Education"), _existing("j3", "Study in Australia")]
    hit = find_overlap(f"{HOST}/study-in-the-uk", "Study in the UK - Admizz Education", existing)
    assert hit["match"] == "title" and hit["job_id"] == "j2" and hit["proof"] == "title_only_not_proven_same_source"
    # the live title has the site suffix, the stored one does not: still only a title match
    assert find_overlap(f"{HOST}/study-in-australia", "Study in Australia - Admizz Education", existing)["job_id"] == "j3"


def test_text_that_merely_resembles_a_stored_chunk_is_not_an_overlap():
    existing = [_existing("j4", "Auto-FAQ: What is the process to apply for a study-abroad program through Admizz Education")]
    assert find_overlap(f"{HOST}/four-documents", "4 Documents Needed for University Applications", existing) is None


def test_no_existing_chunks_means_no_overlap():
    assert find_overlap(f"{HOST}/x", "T", []) is None


# --- cost -----------------------------------------------------------------------------------------------------------------------

def test_the_embedding_estimate_comes_from_the_chunk_manifest_and_states_its_assumptions():
    est = estimate_embeddings([400, 500, 450] + [300] * 98, price_per_million=0.13, batch_size=100)
    assert est["chunks"] == 101 and est["tokens"] == 1350 + 29400
    assert est["api_calls"] == 2                                            # 101 chunks in batches of 100, as ingestion batches them
    assert est["usd"] == pytest.approx(30750 * 0.13 / 1_000_000)
    assert "assumption" in est["note"].lower()


def test_an_empty_manifest_costs_nothing():
    assert estimate_embeddings([]) == {**estimate_embeddings([]), "chunks": 0, "tokens": 0, "api_calls": 0, "usd": 0}


# --- the plan ---------------------------------------------------------------------------------------------------------------------

def test_a_page_already_in_the_knowledge_base_by_url_is_skipped_so_ingesting_twice_adds_nothing():
    plan = plan_ingestion([_page()], [_existing("j1", "x", url=f"{HOST}/study-in-the-uk")])
    assert plan.add == [] and [s["reason"] for s in plan.skip] == ["already_ingested_same_url"]


def test_old_chunks_are_never_retired_automatically_even_on_a_title_match():
    plan = plan_ingestion([_page()], [_existing("j2", "Study in the UK - Admizz Education")])
    assert [p.id for p in plan.add] == ["uk-guide"]
    assert plan.retire == []                                                 # nothing is retired unless an operator confirms the job id
    assert plan.retire_candidates == [{"job_id": "j2", "page_id": "uk-guide", "proof": "title_only_not_proven_same_source"}]


def test_only_confirmed_job_ids_that_are_candidates_are_retired():
    existing = [_existing("j2", "Study in the UK - Admizz Education"), _existing("j9", "Unrelated thing")]
    plan = plan_ingestion([_page()], existing, confirm_retire={"j2", "j9", "ghost"})
    assert plan.retire == ["j2"]                                              # j9 is not a candidate, ghost does not exist
    assert sorted(plan.ignored_confirmations) == ["ghost", "j9"]


def test_link_only_pages_are_never_ingested():
    plan = plan_ingestion([_page("book", f"{HOST}/register", category="contact"), _page("g")], [])
    assert [p.id for p in plan.add] == ["g"] and plan.skip == [{"page_id": "book", "reason": "link_only_category"}]


def test_pages_with_nothing_to_store_are_not_eligible():
    plan = plan_ingestion([_page(chunks=0, warnings=["empty"]), _page("b", f"{HOST}/b", chunks=2)], [])
    assert [p.id for p in plan.add] == ["b"] and plan.skip[0]["reason"] == "no_content"


# --- preflight --------------------------------------------------------------------------------------------------------------------

def test_preflight_passes_a_clean_plan_and_reports_the_cost():
    plan = plan_ingestion([_page(), _page("b", f"{HOST}/b", tokens=300, chunks=2)], [])
    problems, estimate = preflight(plan, [])
    assert problems == [] and estimate["tokens"] == 2400 + 300 and estimate["chunks"] == 8


@pytest.mark.parametrize("make_plan,needle", [
    (lambda: Plan(add=[_page(url="http://admizzeducation.com/x")]), "approved"),
    (lambda: Plan(add=[_page(url="https://evil.com/x")]), "approved"),
    (lambda: Plan(add=[_page(), _page("dup")]), "duplicate"),
    (lambda: Plan(add=[_page()], retire=["ghost"]), "not an existing job"),
    (lambda: Plan(add=[]), "nothing to add"),
])
def test_preflight_refuses_unsafe_plans(make_plan, needle):
    problems, _ = preflight(make_plan(), [_existing("j2", "t")])
    assert any(needle in p for p in problems), problems


def test_preflight_refuses_to_retire_anything_when_nothing_new_would_replace_it():
    problems, _ = preflight(Plan(add=[], retire=["j2"]), [_existing("j2", "t")])
    assert any("nothing to add" in p for p in problems) or any("retire" in p for p in problems)


def test_the_token_budget_guard():
    plan = Plan(add=[_page(tokens=900_000)])
    problems, _ = preflight(plan, [], max_tokens=500_000)
    assert any("budget" in p for p in problems)


# --- execution against a fake store --------------------------------------------------------------------------------------------------

class FakeStore:
    """An in-memory stand-in for Supabase + Pinecone. `fail_on` names a page id whose write fails halfway."""

    def __init__(self, existing=None, fail_on=None, verify_fails=None):
        self.jobs = {}                                    # job_id -> {"url", "complete", "rows", "vectors"}
        for e in existing or []:
            self.jobs[e.job_id] = {"url": e.source_url, "complete": True, "rows": e.chunks, "vectors": e.chunks}
        self.fail_on, self.verify_fails, self.log, self.n = fail_on, verify_fails or set(), [], 0

    async def completed_urls(self):
        return {j["url"] for j in self.jobs.values() if j["complete"] and j["url"]}

    async def add_page(self, page):
        self.n += 1
        job_id = f"new{self.n}"
        self.log.append(("add", page.id))
        self.jobs[job_id] = {"url": page.canonical_url, "complete": False, "rows": page.chunks, "vectors": 0}   # Postgres first
        if page.id == self.fail_on:
            raise PageWriteError("vector store timed out", job_id=job_id)                                         # rows exist, no vectors
        self.jobs[job_id].update(vectors=page.chunks, complete=True)
        return AddResult(job_id=job_id, chunks=page.chunks)

    async def verify_page(self, job_id, expected_chunks):
        self.log.append(("verify", job_id))
        job = self.jobs[job_id]
        return job["rows"] == expected_chunks and job["vectors"] == expected_chunks and job["url"] not in self.verify_fails

    async def retire_job(self, job_id):
        self.log.append(("retire", job_id))
        self.jobs.pop(job_id, None)


def _plan(*pages, retire=()):
    return Plan(add=list(pages), retire=list(retire))


@pytest.mark.asyncio
async def test_new_pages_are_added_and_verified_before_any_old_chunk_is_retired():
    store = FakeStore(existing=[_existing("old1", "Study in the UK - Admizz Education")])
    log = await execute_plan(_plan(_page(), _page("b", f"{HOST}/b"), retire=["old1"]), store)
    assert log.status == "completed" and [p["status"] for p in log.pages] == ["added", "added"]
    ops = [op for op in store.log]
    assert ops.index(("retire", "old1")) > max(i for i, o in enumerate(ops) if o[0] == "verify")      # old content leaves last
    assert "old1" not in store.jobs and len(await store.completed_urls()) == 2


@pytest.mark.asyncio
async def test_running_the_same_plan_twice_is_idempotent():
    store = FakeStore()
    plan = _plan(_page(), _page("b", f"{HOST}/b"))
    await execute_plan(plan, store)
    again = await execute_plan(plan, store)
    assert [p["status"] for p in again.pages] == ["skipped_already_ingested"] * 2
    assert len(store.jobs) == 2 and [o for o in store.log if o[0] == "add"] == [("add", "uk-guide"), ("add", "b")]


@pytest.mark.asyncio
async def test_a_failed_page_stops_the_batch_cleans_its_partial_write_and_retires_nothing():
    store = FakeStore(existing=[_existing("old1", "Study in the UK - Admizz Education")], fail_on="b")
    log = await execute_plan(_plan(_page(), _page("b", f"{HOST}/b"), _page("c", f"{HOST}/c"), retire=["old1"]), store)
    assert log.status == "stopped" and [p["status"] for p in log.pages] == ["added", "failed"]
    assert "old1" in store.jobs                                                  # the old content is still there: no gap
    assert all(j["complete"] for j in store.jobs.values())                      # the half-written page was cleaned up
    assert ("add", "c") not in store.log                                         # and nothing after it was attempted


@pytest.mark.asyncio
async def test_a_batch_is_resumed_without_repeating_finished_pages():
    store = FakeStore(fail_on="b")
    plan = _plan(_page(), _page("b", f"{HOST}/b"), _page("c", f"{HOST}/c"))
    await execute_plan(plan, store)                       # a is added, b fails and is cleaned, c never starts
    store.fail_on = None                                  # the outage is over
    log = await execute_plan(plan, store)
    assert [p["status"] for p in log.pages] == ["skipped_already_ingested", "added", "added"] and log.status == "completed"
    assert len(await store.completed_urls()) == 3 and len(store.jobs) == 3


@pytest.mark.asyncio
async def test_a_page_that_fails_verification_counts_as_failed_and_is_cleaned():
    store = FakeStore(verify_fails={f"{HOST}/b"})
    log = await execute_plan(_plan(_page(), _page("b", f"{HOST}/b")), store, )
    assert log.pages[1]["status"] == "failed" and "verification" in log.pages[1]["error"]
    assert f"{HOST}/b" not in await store.completed_urls() and len(store.jobs) == 1


@pytest.mark.asyncio
async def test_without_stop_on_error_the_rest_of_the_batch_still_runs_but_nothing_is_retired():
    store = FakeStore(existing=[_existing("old1", "t")], fail_on="b")
    log = await execute_plan(_plan(_page(), _page("b", f"{HOST}/b"), _page("c", f"{HOST}/c"), retire=["old1"]), store, stop_on_error=False)
    assert [p["status"] for p in log.pages] == ["added", "failed", "added"] and "old1" in store.jobs


@pytest.mark.asyncio
async def test_an_unsafe_plan_is_refused_before_anything_is_written():
    store = FakeStore()
    log = await execute_plan(_plan(_page(url="https://evil.com/x")), store)
    assert log.status == "refused" and store.log == [] and log.problems


# --- detecting a half-written ingestion -----------------------------------------------------------------------------------------------

def test_jobs_whose_postgres_rows_and_vectors_disagree_are_reported():
    rows = {"a": 6, "b": 3, "c": 2, "d": 1}
    vectors = {"a": 6, "b": 0, "c": 5}                     # b: rows without vectors, c: more vectors than rows, d: no vectors at all
    assert find_inconsistent_jobs(rows, vectors) == [("b", 3, 0), ("c", 2, 5), ("d", 1, 0)]


def test_consistent_jobs_report_nothing():
    assert find_inconsistent_jobs({"a": 2}, {"a": 2}) == []


# --- how the EXISTING ingestion service behaves (fake clients, no I/O) -------------------------------------------------------------------

class _FakeDb:
    def __init__(self, log):
        self.added, self.log = [], log

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.log.append("commit")

    async def execute(self, *a, **k):
        self.log.append("execute")


def _service(log, fail_upsert=False):
    from app.services.ingestion import IngestionService

    async def create_embeddings(texts):
        log.append(f"embed:{len(texts)}")
        return [[0.1] * 3 for _ in texts]

    async def upsert_vectors(vectors, namespace):
        log.append("upsert")
        if fail_upsert:
            raise RuntimeError("pinecone down")
        service.upserted.extend(vectors)

    service = IngestionService.__new__(IngestionService)
    service.embedding_service = SimpleNamespace(create_embeddings=create_embeddings)
    service.vector_store = SimpleNamespace(upsert_vectors=upsert_vectors)
    service.upserted = []
    return service


def _chunks(n=2, url=f"{HOST}/study-in-the-uk", title="Study in the UK - Admizz Education"):
    return [{"content": f"chunk {i}", "chunk_index": i, "token_count": 10, "source_url": url, "source_title": title} for i in range(n)]


@pytest.mark.asyncio
async def test_the_existing_pipeline_carries_the_canonical_url_and_title_into_both_stores():
    log = []
    service, db = _service(log), _FakeDb(log)
    job = SimpleNamespace(id=uuid.uuid4(), customer_id=uuid.uuid4())
    await service._process_chunks(db=db, job=job, site_id="admizz-test", chunks=_chunks())
    assert [(r.source_url, r.source_title) for r in db.added] == [(f"{HOST}/study-in-the-uk", "Study in the UK - Admizz Education")] * 2
    assert [(v["metadata"]["source_url"], v["metadata"]["source_title"]) for v in service.upserted] == \
           [(f"{HOST}/study-in-the-uk", "Study in the UK - Admizz Education")] * 2
    assert all(v["id"] == f"{job.id}_{i}" for i, v in enumerate(service.upserted))      # ids are job id + chunk number: no per-source id


@pytest.mark.asyncio
async def test_the_existing_pipeline_commits_postgres_before_pinecone_so_a_failure_leaves_rows_without_vectors():
    log = []
    service, db = _service(log, fail_upsert=True), _FakeDb(log)
    with pytest.raises(RuntimeError):
        await service._process_chunks(db=db, job=SimpleNamespace(id=uuid.uuid4(), customer_id=uuid.uuid4()), site_id="s", chunks=_chunks())
    assert log.index("commit") < log.index("upsert") and len(db.added) == 2 and service.upserted == []


@pytest.mark.asyncio
async def test_the_existing_pipeline_is_append_only_so_the_same_page_ingested_twice_is_stored_twice():
    log = []
    service, db = _service(log), _FakeDb(log)
    for _ in range(2):
        await service._process_chunks(db=db, job=SimpleNamespace(id=uuid.uuid4(), customer_id=uuid.uuid4()), site_id="s", chunks=_chunks())
    assert len(db.added) == 4 and len({v["id"] for v in service.upserted}) == 4         # new job id each time: nothing is overwritten


@pytest.mark.asyncio
async def test_embeddings_are_requested_in_batches_of_one_hundred():
    log = []
    service, db = _service(log), _FakeDb(log)
    await service._process_chunks(db=db, job=SimpleNamespace(id=uuid.uuid4(), customer_id=uuid.uuid4()), site_id="s", chunks=_chunks(141))
    assert [e for e in log if e.startswith("embed")] == ["embed:100", "embed:41"]
