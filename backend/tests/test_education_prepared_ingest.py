"""The prepared-pages write adapter, proved against fakes only. Nothing here touches a database, Pinecone, an embedding service or the
network, and no real credential is used. Covered: the target lock, deterministic page identity, idempotent reruns, resuming after a
failure, half-written pages, preflight refusals, approval tied to the exact manifest, and add-verify-retire with exact job ids."""
import hashlib
import json
import uuid
from datetime import date

import pytest

from app.services import education_prepared_ingest as pi
from app.services.education_ingest_plan import PageWriteError
from app.services.education_page_dispositions import READY, REVIEW, Disposition, dispositions_for, load_manifest
from app.services.education_prepared_ingest import (
    ALLOWED_TARGETS, ExecutionApproval, JobState, PreparedPage, Target, TargetInfo, Verification, WriteResult, check_approval,
    manifest_sha256, retire_confirmed_jobs, run_prepared_ingestion, source_job_id, validate_target,
)
from app.services.education_sources import SOURCES_DIR

HOST = "https://admizzeducation.com"
CUSTOMER = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
TARGET = Target(site_id="admizz-test", customer_id=CUSTOMER, namespace="admizz-test")
INFO = TargetInfo(site_id="admizz-test", customer_id=CUSTOMER, website_type="education", namespace="admizz-test")
SNAPSHOT = SOURCES_DIR / "admizz-test.manifest.json"


def _chunks(n, url, title):
    return [{"content": f"chunk {i} of {url}", "chunk_index": i, "token_count": 100, "source_url": url, "source_title": title} for i in range(n)]


def _page(pid="uk-visa-fee", path="answers/uk-student-visa-fee-nepal", n=2, text=None, title="UK Student Visa Fee and Health Surcharge: Short Answer"):
    url = f"{HOST}/{path}"
    text = text or f"text of {pid}"
    return PreparedPage(id=pid, canonical_url=url, title=title, chunks=_chunks(n, url, title),
                        content_sha256=hashlib.sha256(text.encode()).hexdigest(), tokens=100 * n, category="visa", country="uk", kind="answer")


def _manifest(*pages):
    return {"dry_run": True, "pages": [{"id": p.id, "canonical_url": p.canonical_url, "chunks": len(p.chunks), "tokens": p.tokens,
                                        "eligible_for_ingestion": True, "content_class": "dated", "content_sha256": p.content_sha256,
                                        "verified": False} for p in pages], "plan": {"retire_candidates": []}}


def _ready(*pages):
    return {p.id: Disposition(p.id, READY) for p in pages}


def _approval(manifest, pages, **kw):
    return ExecutionApproval(manifest_sha256=manifest_sha256(manifest), site_id="admizz-test", approved_by="Anish",
                             page_ids=tuple(sorted(p.id for p in pages)), **kw)


# --- an in-memory stand-in for Postgres + Pinecone ----------------------------------------------------------------------------------

class FakeStore:
    writes_enabled = True

    def __init__(self, info=INFO, fail_vectors_for=(), fail_cleanup=False, forbid_writes=False):
        self.info, self.fail_vectors_for, self.fail_cleanup, self.forbid_writes = info, set(fail_vectors_for), fail_cleanup, forbid_writes
        self.jobs: dict[str, dict] = {}     # job_id -> {url, title, status, expected, rows(list of vector ids), vectors(set of ids)}
        self.log: list[tuple] = []

    def seed_job(self, job_id, url, title="old", rows=1, vectors=None, status="completed"):
        ids = [f"{job_id}_{i}" for i in range(rows)]
        self.jobs[job_id] = {"url": url, "title": title, "status": status, "expected": rows, "rows": ids,
                             "vectors": set(ids) if vectors is None else {f"{job_id}_{i}" for i in range(vectors)}}

    def _write_guard(self, what):
        self.log.append((what,))
        if self.forbid_writes:
            raise AssertionError(f"a read-only run must not call {what}")

    async def describe_target(self):
        return self.info

    async def jobs_for_url(self, url):
        return [self._state(j) for j, v in self.jobs.items() if v["url"] == url]

    def _state(self, job_id):
        j = self.jobs[job_id]
        return JobState(job_id=job_id, status=j["status"], source_url=j["url"], title=j["title"], chunks_expected=j["expected"],
                        rows=len(j["rows"]), vectors=len(j["vectors"]))

    async def write_page(self, page):
        self._write_guard("write_page")
        job_id = str(page.job_id)
        ids = [f"{job_id}_{i}" for i in range(len(page.chunks))]
        self.jobs[job_id] = {"url": page.canonical_url, "title": page.title, "status": "processing", "expected": len(page.chunks),
                             "rows": ids, "vectors": set()}                                # Postgres first
        if page.id in self.fail_vectors_for:
            self.jobs[job_id]["status"] = "failed"
            raise PageWriteError("vector store timed out", job_id=job_id)
        self.jobs[job_id].update(vectors=set(ids), status="completed")
        return WriteResult(job_id=job_id, rows=len(ids), vectors=len(ids))

    async def verify_job(self, job_id, expected_chunks):
        self.log.append(("verify", job_id))
        j = self.jobs.get(job_id)
        return Verification(rows=len(j["rows"]) if j else 0, vectors=len(j["vectors"]) if j else 0)

    async def cleanup_job(self, job_id):
        self._write_guard("cleanup_job")
        if self.fail_cleanup:
            raise RuntimeError("cleanup failed")
        self.jobs.pop(job_id, None)

    async def job_vector_ids(self, job_id):
        return list(self.jobs[job_id]["rows"]) if job_id in self.jobs else []

    async def delete_vectors(self, ids):
        self._write_guard("delete_vectors")
        self.log.append(("delete_vectors", tuple(ids)))
        for j in self.jobs.values():
            j["vectors"] -= set(ids)

    async def delete_job(self, job_id):
        self._write_guard("delete_job")
        self.log.append(("delete_job", job_id))
        self.jobs.pop(job_id, None)


# --- the target lock ----------------------------------------------------------------------------------------------------------------

def test_only_admizz_test_is_an_allowed_target():
    assert ALLOWED_TARGETS == frozenset({"admizz-test"})


def test_a_matching_target_has_no_problems():
    assert validate_target(TARGET, INFO) == []


@pytest.mark.parametrize("target,info,needle", [
    (Target("dental-city", CUSTOMER, "dental-city"), TargetInfo("dental-city", CUSTOMER, "education", "dental-city"), "not an allowed target"),
    (Target("admizz-test", CUSTOMER, "other-namespace"), INFO, "namespace"),
    (TARGET, TargetInfo("admizz-test", uuid.uuid4(), "education", "admizz-test"), "customer"),
    (TARGET, TargetInfo("someone-else", CUSTOMER, "education", "admizz-test"), "site_id"),
    (TARGET, TargetInfo("admizz-test", CUSTOMER, "clinic", "admizz-test"), "education"),
    (TARGET, TargetInfo("admizz-test", CUSTOMER, "education", "other-namespace"), "namespace"),
])
def test_a_wrong_tenant_customer_namespace_or_type_is_refused(target, info, needle):
    assert any(needle in p for p in validate_target(target, info))


@pytest.mark.asyncio
async def test_a_run_against_the_wrong_target_is_refused_before_anything_is_read_or_written():
    page, store = _page(), FakeStore(info=TargetInfo("dental-city", CUSTOMER, "clinic", "dental-city"))
    m = _manifest(page)
    report = await run_prepared_ingestion([page], store, manifest=m, dispositions=_ready(page), target=TARGET, mode="execute",
                                          approval=_approval(m, [page]))
    assert report.status == "refused" and any("target" in p.lower() or "allowed" in p for p in report.problems)
    assert store.log == [] and store.jobs == {}


# --- identity -------------------------------------------------------------------------------------------------------------------------

def test_a_page_has_a_deterministic_job_id_from_its_site_url_and_content():
    p = _page()
    assert p.job_id == source_job_id("admizz-test", p.canonical_url, p.content_sha256) == _page().job_id
    assert isinstance(p.job_id, uuid.UUID)


def test_changed_content_or_a_different_url_or_tenant_gives_a_different_job_id():
    base = _page().job_id
    assert _page(text="different text").job_id != base
    assert _page(path="answers/other").job_id != base
    assert source_job_id("other-tenant", _page().canonical_url, _page().content_sha256) != base


def test_prepared_page_chunks_carry_the_canonical_url_and_title():
    p = _page(n=3)
    assert [(c["source_url"], c["source_title"]) for c in p.chunks] == [(p.canonical_url, p.title)] * 3


# --- dry run: reads only, writes nothing -------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_dry_run_reports_the_plan_and_calls_no_write():
    pages = [_page("a", "a"), _page("b", "b")]
    store = FakeStore(forbid_writes=True)
    report = await run_prepared_ingestion(pages, store, manifest=_manifest(*pages), dispositions=_ready(*pages), target=TARGET)
    assert report.mode == "dry_run" and report.status == "dry_run" and [p.state for p in report.pages] == ["new", "new"]
    assert [p.action for p in report.pages] == ["would_add", "would_add"] and store.jobs == {}
    assert report.estimate["chunks"] == 4


@pytest.mark.asyncio
async def test_a_dry_run_needs_no_approval_but_execution_does():
    page = _page()
    m = _manifest(page)
    refused = await run_prepared_ingestion([page], FakeStore(), manifest=m, dispositions=_ready(page), target=TARGET, mode="execute")
    assert refused.status == "refused" and any("approval" in p for p in refused.problems)


@pytest.mark.asyncio
async def test_an_unknown_mode_is_refused():
    page = _page()
    report = await run_prepared_ingestion([page], FakeStore(), manifest=_manifest(page), dispositions=_ready(page), target=TARGET, mode="yolo")
    assert report.status == "refused"


# --- approval is tied to the exact manifest -----------------------------------------------------------------------------------------------

def test_the_manifest_hash_changes_when_a_page_url_size_or_class_changes():
    page = _page()
    base = manifest_sha256(_manifest(page))
    assert manifest_sha256(_manifest(page)) == base
    changed = _manifest(page)
    changed["pages"][0]["chunks"] += 1
    assert manifest_sha256(changed) != base
    changed = _manifest(page)
    changed["pages"][0]["canonical_url"] += "x"
    assert manifest_sha256(changed) != base
    reordered = _manifest(_page("a", "a"), _page("b", "b"))
    reordered["pages"].reverse()
    assert manifest_sha256(reordered) == manifest_sha256(_manifest(_page("a", "a"), _page("b", "b")))   # order does not matter


def test_an_approval_for_another_manifest_site_or_page_list_is_refused():
    page, other = _page(), _page("zzz", "zzz")
    m = _manifest(page)
    good = _approval(m, [page])
    assert check_approval(good, m, [page], TARGET) == []
    assert check_approval(_approval(_manifest(other), [page]), m, [page], TARGET)                       # hash of a different manifest
    assert check_approval(ExecutionApproval(manifest_sha256(m), "dental-city", "A", (page.id,)), m, [page], TARGET)
    assert check_approval(_approval(m, [page, other]), m, [page], TARGET)                               # approves pages that are not planned
    assert check_approval(ExecutionApproval(manifest_sha256(m), "admizz-test", "  ", (page.id,)), m, [page], TARGET)   # nobody named


@pytest.mark.asyncio
async def test_execution_with_a_stale_approval_changes_nothing():
    page = _page()
    m = _manifest(page)
    approval = _approval(m, [page])
    m["pages"][0]["chunks"] = 99                        # the manifest was edited after it was approved
    store = FakeStore()
    report = await run_prepared_ingestion([page], store, manifest=m, dispositions=_ready(page), target=TARGET, mode="execute", approval=approval)
    assert report.status == "refused" and store.jobs == {}


# --- preflight: unsafe or ambiguous plans are refused -------------------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("disposition", [Disposition("uk-visa-fee", REVIEW, ("university_names_unverified",)),
                                         Disposition("uk-visa-fee", "excluded", ("link_only_category",)),
                                         Disposition("uk-visa-fee", "undecided", ("manifest_incomplete:content_class",))])
async def test_only_ready_pages_can_be_ingested(disposition):
    page = _page()
    report = await run_prepared_ingestion([page], FakeStore(), manifest=_manifest(page), dispositions={page.id: disposition}, target=TARGET)
    assert report.status == "refused" and any("not ready" in p for p in report.problems)


@pytest.mark.asyncio
async def test_a_page_with_no_disposition_is_refused():
    page = _page()
    report = await run_prepared_ingestion([page], FakeStore(), manifest=_manifest(page), dispositions={}, target=TARGET)
    assert report.status == "refused" and any("no disposition" in p for p in report.problems)


@pytest.mark.asyncio
@pytest.mark.parametrize("make,needle", [
    (lambda: PreparedPage("x", "http://admizzeducation.com/x", "T", _chunks(1, "u", "T"), "h" * 64, 100), "approved"),
    (lambda: PreparedPage("x", "https://evil.com/x", "T", _chunks(1, "u", "T"), "h" * 64, 100), "approved"),
    (lambda: PreparedPage("x", f"{HOST}/x", "T" * 300, _chunks(1, "u", "T"), "h" * 64, 100), "title"),
    (lambda: PreparedPage("x", f"{HOST}/x", "T", [], "h" * 64, 0), "no chunks"),
    (lambda: PreparedPage("x", f"{HOST}/x", "", _chunks(1, "u", "T"), "h" * 64, 100), "title"),
])
async def test_preflight_refuses_unsafe_pages(make, needle):
    page = make()
    report = await run_prepared_ingestion([page], FakeStore(), manifest=_manifest(page), dispositions=_ready(page), target=TARGET)
    assert report.status == "refused" and any(needle in p for p in report.problems), report.problems


@pytest.mark.asyncio
async def test_two_pages_with_the_same_canonical_url_are_refused():
    a, b = _page("a", "same"), _page("b", "same", text="other")
    report = await run_prepared_ingestion([a, b], FakeStore(), manifest=_manifest(a, b), dispositions=_ready(a, b), target=TARGET)
    assert report.status == "refused" and any("duplicate" in p for p in report.problems)


@pytest.mark.asyncio
async def test_a_page_that_changed_since_the_manifest_is_refused():
    page = _page()
    m = _manifest(page)
    m["pages"][0]["content_sha256"] = "0" * 64
    report = await run_prepared_ingestion([page], FakeStore(), manifest=m, dispositions=_ready(page), target=TARGET)
    assert report.status == "refused" and any("changed since the manifest" in p for p in report.problems)
    m2 = _manifest(page)
    m2["pages"][0]["chunks"] = 7
    assert any("changed since the manifest" in p for p in (await run_prepared_ingestion([page], FakeStore(), manifest=m2, dispositions=_ready(page), target=TARGET)).problems)


@pytest.mark.asyncio
async def test_a_page_missing_from_the_manifest_is_refused():
    page = _page()
    report = await run_prepared_ingestion([page], FakeStore(), manifest={"dry_run": True, "pages": []}, dispositions=_ready(page), target=TARGET)
    assert report.status == "refused" and any("not in the manifest" in p for p in report.problems)


@pytest.mark.asyncio
async def test_a_plan_over_the_token_budget_is_refused():
    page = _page(n=2)
    page.tokens = 900_000
    report = await run_prepared_ingestion([page], FakeStore(), manifest=_manifest(page), dispositions=_ready(page), target=TARGET)
    assert report.status == "refused" and any("budget" in p for p in report.problems)


# --- execution, idempotency, recovery ------------------------------------------------------------------------------------------------------

async def _execute(pages, store, **kw):
    m = kw.pop("manifest", None) or _manifest(*pages)
    return await run_prepared_ingestion(pages, store, manifest=m, dispositions=_ready(*pages), target=TARGET, mode="execute",
                                        approval=kw.pop("approval", None) or _approval(m, pages), **kw), m


@pytest.mark.asyncio
async def test_new_pages_are_written_and_verified():
    pages = [_page("a", "a", n=2), _page("b", "b", n=3)]
    store = FakeStore()
    report, _ = await _execute(pages, store)
    assert report.status == "completed" and [p.action for p in report.pages] == ["added", "added"]
    assert [(p.rows, p.vectors) for p in report.pages] == [(2, 2), (3, 3)] and report.all_verified
    assert {j["url"] for j in store.jobs.values()} == {p.canonical_url for p in pages}
    assert all(p.job_id == str(pg.job_id) for p, pg in zip(report.pages, pages))                      # the deterministic ids were used


@pytest.mark.asyncio
async def test_running_the_same_batch_again_adds_nothing():
    pages = [_page("a", "a"), _page("b", "b")]
    store = FakeStore()
    await _execute(pages, store)
    jobs_before, writes_before = dict(store.jobs), [e for e in store.log if e[0] == "write_page"]
    again, _ = await _execute(pages, store)
    assert [p.action for p in again.pages] == ["skipped_already_ingested"] * 2 and again.status == "completed" and again.all_verified
    assert store.jobs == jobs_before and [e for e in store.log if e[0] == "write_page"] == writes_before


@pytest.mark.asyncio
async def test_a_failed_page_is_cleaned_up_and_the_batch_stops_with_nothing_half_written():
    pages = [_page("a", "a"), _page("b", "b"), _page("c", "c")]
    store = FakeStore(fail_vectors_for={"b"})
    report, _ = await _execute(pages, store)
    assert report.status == "stopped" and [p.action for p in report.pages] == ["added", "failed"] and not report.all_verified
    assert "vector store timed out" in report.pages[1].error
    assert len(store.jobs) == 1 and all(j["status"] == "completed" for j in store.jobs.values())      # b's half-written job is gone
    assert not any(e == ("write_page",) and False for e in store.log)


@pytest.mark.asyncio
async def test_a_stopped_batch_resumes_where_it_stopped():
    pages = [_page("a", "a"), _page("b", "b"), _page("c", "c")]
    store = FakeStore(fail_vectors_for={"b"})
    await _execute(pages, store)
    store.fail_vectors_for = set()
    report, _ = await _execute(pages, store)
    assert [p.action for p in report.pages] == ["skipped_already_ingested", "added", "added"] and report.status == "completed"
    assert len(store.jobs) == 3


@pytest.mark.asyncio
async def test_a_crash_that_left_rows_without_vectors_is_detected_and_not_reported_as_success():
    page = _page(n=3)
    store = FakeStore()
    store.seed_job(str(page.job_id), page.canonical_url, rows=3, vectors=0, status="processing")      # a previous run died after Postgres
    m = _manifest(page)
    report = await run_prepared_ingestion([page], store, manifest=m, dispositions=_ready(page), target=TARGET, mode="execute", approval=_approval(m, [page]))
    assert report.pages[0].state == "incomplete_own_job" and report.pages[0].action == "needs_recovery"
    assert report.status != "completed" and not report.all_verified
    assert store.jobs[str(page.job_id)]["status"] == "processing"                                       # nothing was touched without resume=True


@pytest.mark.asyncio
async def test_with_resume_an_incomplete_own_job_is_cleaned_then_rewritten_and_verified():
    page = _page(n=3)
    store = FakeStore()
    store.seed_job(str(page.job_id), page.canonical_url, rows=3, vectors=1, status="failed")
    report, _ = await _execute([page], store, resume=True)
    assert report.pages[0].action == "recovered_and_added" and report.all_verified
    j = store.jobs[str(page.job_id)]
    assert j["status"] == "completed" and len(j["rows"]) == 3 and len(j["vectors"]) == 3 and len(store.jobs) == 1


@pytest.mark.asyncio
async def test_a_failed_cleanup_is_reported_and_the_batch_stops():
    page = _page()
    store = FakeStore(fail_vectors_for={page.id}, fail_cleanup=True)
    report, _ = await _execute([page], store)
    assert report.status == "stopped" and "cleanup" in report.pages[0].error.lower()


@pytest.mark.asyncio
async def test_a_page_that_fails_verification_is_not_reported_as_added():
    class ShortStore(FakeStore):
        async def verify_job(self, job_id, expected_chunks):
            return Verification(rows=expected_chunks, vectors=expected_chunks - 1)         # one vector went missing
    report, _ = await _execute([_page(n=3)], ShortStore())
    assert report.pages[0].action == "failed" and "verification" in report.pages[0].error and not report.all_verified and report.status == "stopped"


@pytest.mark.asyncio
async def test_an_existing_job_for_the_same_url_with_different_content_is_reported_for_review_and_never_touched():
    page = _page()
    store = FakeStore()
    store.seed_job("old-job-1", page.canonical_url, title="Older version", rows=2)
    report, _ = await _execute([page], store)
    assert report.pages[0].state == "ambiguous_same_url_different_content" and report.pages[0].action == "needs_review"
    assert report.pages[0].other_job_ids == ["old-job-1"] and report.status == "completed_with_review_items"
    assert "old-job-1" in store.jobs and not [e for e in store.log if e[0] in ("write_page", "delete_job", "delete_vectors", "cleanup_job")]


@pytest.mark.asyncio
async def test_other_pages_still_proceed_when_one_page_needs_review_but_the_batch_is_not_called_complete():
    a, b = _page("a", "a"), _page("b", "b")
    store = FakeStore()
    store.seed_job("old", a.canonical_url, rows=1)
    report, _ = await _execute([a, b], store)
    assert [p.action for p in report.pages] == ["needs_review", "added"] and report.status == "completed_with_review_items"
    assert not report.all_verified


@pytest.mark.asyncio
async def test_a_completed_page_with_an_older_job_for_the_same_url_is_done_and_the_older_job_is_only_noted():
    page = _page()
    store = FakeStore()
    store.seed_job(str(page.job_id), page.canonical_url, rows=2)
    store.seed_job("old-job-2", page.canonical_url, rows=1)
    report, _ = await _execute([page], store)
    assert report.pages[0].action == "skipped_already_ingested" and report.pages[0].other_job_ids == ["old-job-2"]
    assert "old-job-2" in store.jobs


@pytest.mark.asyncio
async def test_an_old_job_whose_rows_and_vectors_disagree_is_reported_not_repaired():
    page = _page()
    store = FakeStore()
    store.seed_job("old-job-3", page.canonical_url, rows=3, vectors=0)
    report, _ = await _execute([page], store)
    assert report.pages[0].inconsistent_other_jobs == [("old-job-3", 3, 0)]
    assert store.jobs["old-job-3"]["vectors"] == set()                                  # reported only


@pytest.mark.asyncio
async def test_pages_are_ingested_in_the_order_of_their_dispositions():
    a, b = _page("a", "a"), _page("b", "b")
    store = FakeStore()
    m = _manifest(a, b)
    ds = {a.id: Disposition("a", READY), b.id: Disposition("b", READY)}
    report = await run_prepared_ingestion([b, a], store, manifest=m, dispositions=ds, target=TARGET, mode="execute",
                                          approval=_approval(m, [a, b]), order=["a", "b"])
    assert [p.page_id for p in report.pages] == ["a", "b"]


# --- retirement: planned and checked, with exact ids, only after verification ---------------------------------------------------------------

def _two_old(store, page):
    store.seed_job("old-uk", "u1", title="Study in the UK - Admizz Education", rows=2)
    store.seed_job("old-us", "u2", title="Study in the USA - Admizz Education", rows=1)
    return [{"job_id": "old-uk", "page_id": page.id, "proof": "title_only_not_proven_same_source"},
            {"job_id": "old-us", "page_id": "other", "proof": "title_only_not_proven_same_source"}]


async def _ok(page):
    return True


@pytest.mark.asyncio
async def test_retirement_is_planned_for_exact_confirmed_job_ids_and_their_vector_ids_without_executing():
    page, store = _page("uk-guide", "study-in-the-uk"), FakeStore()
    cands = _two_old(store, page)
    report, m = await _execute([page], store)
    approval = _approval(m, [page], confirmed_retire_job_ids=("old-uk",))
    plan = await retire_confirmed_jobs(store, report=report, candidates=cands, approval=approval, retrieval_check=_ok, pages=[page])
    assert plan.executed is False and plan.status == "planned" and plan.problems == []
    assert plan.jobs == [{"job_id": "old-uk", "vector_ids": ["old-uk_0", "old-uk_1"]}]
    assert "old-uk" in store.jobs and "old-us" in store.jobs                                           # nothing deleted in a plan


@pytest.mark.asyncio
async def test_execution_deletes_vectors_first_then_the_job_and_touches_only_the_confirmed_id():
    page, store = _page("uk-guide", "study-in-the-uk"), FakeStore()
    cands = _two_old(store, page)
    report, m = await _execute([page], store)
    store.log.clear()
    result = await retire_confirmed_jobs(store, report=report, candidates=cands, pages=[page], retrieval_check=_ok, execute=True,
                                         approval=_approval(m, [page], confirmed_retire_job_ids=("old-uk",)))
    assert result.status == "retired" and result.retired == ["old-uk"]
    ops = [e for e in store.log if e[0] in ("delete_vectors", "delete_job") and len(e) > 1]
    assert ops == [("delete_vectors", ("old-uk_0", "old-uk_1")), ("delete_job", "old-uk")]
    assert "old-uk" not in store.jobs and "old-us" in store.jobs and str(page.job_id) in store.jobs


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmed", [(), ("ghost",), ("old-uk", "ghost"), ("OLD-UK",)])
async def test_only_exact_confirmed_ids_that_are_candidates_are_accepted(confirmed):
    page, store = _page("uk-guide", "study-in-the-uk"), FakeStore()
    cands = _two_old(store, page)
    report, m = await _execute([page], store)
    result = await retire_confirmed_jobs(store, report=report, candidates=cands, pages=[page], retrieval_check=_ok, execute=True,
                                         approval=_approval(m, [page], confirmed_retire_job_ids=confirmed))
    assert result.status == "refused" and result.retired == [] and "old-uk" in store.jobs


@pytest.mark.asyncio
async def test_nothing_is_retired_while_any_replacement_is_unverified_failed_or_awaiting_review():
    a, b = _page("uk-guide", "study-in-the-uk"), _page("b", "b")
    for store in (FakeStore(fail_vectors_for={"b"}),):
        cands = _two_old(store, a)
        report, m = await _execute([a, b], store)
        result = await retire_confirmed_jobs(store, report=report, candidates=cands, pages=[a, b], retrieval_check=_ok, execute=True,
                                             approval=_approval(m, [a, b], confirmed_retire_job_ids=("old-uk",)))
        assert result.status == "refused" and any("verified" in p for p in result.problems) and "old-uk" in store.jobs
    store = FakeStore()
    store.seed_job("older", a.canonical_url, rows=1)                     # makes page a "needs_review"
    cands = _two_old(store, a)
    report, m = await _execute([a], store)
    result = await retire_confirmed_jobs(store, report=report, candidates=cands, pages=[a], retrieval_check=_ok, execute=True,
                                         approval=_approval(m, [a], confirmed_retire_job_ids=("old-uk",)))
    assert result.status == "refused" and "old-uk" in store.jobs


@pytest.mark.asyncio
async def test_a_dry_run_report_can_never_authorise_retirement():
    page, store = _page("uk-guide", "study-in-the-uk"), FakeStore()
    cands = _two_old(store, page)
    m = _manifest(page)
    dry = await run_prepared_ingestion([page], store, manifest=m, dispositions=_ready(page), target=TARGET)
    result = await retire_confirmed_jobs(store, report=dry, candidates=cands, pages=[page], retrieval_check=_ok, execute=True,
                                         approval=_approval(m, [page], confirmed_retire_job_ids=("old-uk",)))
    assert result.status == "refused" and "old-uk" in store.jobs


@pytest.mark.asyncio
async def test_retirement_waits_for_the_retrieval_check_of_the_replacement():
    page, store = _page("uk-guide", "study-in-the-uk"), FakeStore()
    cands = _two_old(store, page)
    report, m = await _execute([page], store)

    async def fails(p):
        return False
    result = await retire_confirmed_jobs(store, report=report, candidates=cands, pages=[page], retrieval_check=fails, execute=True,
                                         approval=_approval(m, [page], confirmed_retire_job_ids=("old-uk",)))
    assert result.status == "refused" and any("retrieval" in p for p in result.problems) and "old-uk" in store.jobs

    async def explodes(p):
        raise RuntimeError("search is down")
    result = await retire_confirmed_jobs(store, report=report, candidates=cands, pages=[page], retrieval_check=explodes, execute=True,
                                         approval=_approval(m, [page], confirmed_retire_job_ids=("old-uk",)))
    assert result.status == "refused" and "old-uk" in store.jobs


@pytest.mark.asyncio
async def test_retirement_without_a_retrieval_check_is_refused():
    page, store = _page("uk-guide", "study-in-the-uk"), FakeStore()
    cands = _two_old(store, page)
    report, m = await _execute([page], store)
    result = await retire_confirmed_jobs(store, report=report, candidates=cands, pages=[page], retrieval_check=None, execute=True,
                                         approval=_approval(m, [page], confirmed_retire_job_ids=("old-uk",)))
    assert result.status == "refused" and "old-uk" in store.jobs


@pytest.mark.asyncio
async def test_a_failure_while_retiring_stops_without_touching_the_next_job():
    page, store = _page("uk-guide", "study-in-the-uk"), FakeStore()
    cands = _two_old(store, page)
    cands[1]["page_id"] = page.id
    report, m = await _execute([page], store)

    class Failing(FakeStore):
        pass
    orig = store.delete_job

    async def boom(job_id):
        if job_id == "old-uk":
            raise RuntimeError("database unavailable")
        await orig(job_id)
    store.delete_job = boom
    result = await retire_confirmed_jobs(store, report=report, candidates=cands, pages=[page], retrieval_check=_ok, execute=True,
                                         approval=_approval(m, [page], confirmed_retire_job_ids=("old-uk", "old-us")))
    assert result.status == "stopped" and result.retired == [] and "old-us" in store.jobs


def test_no_namespace_wide_delete_exists_anywhere_in_the_adapter():
    import inspect
    source = inspect.getsource(pi)
    assert "delete_customer_data" not in source and "delete_namespace" not in source and "delete_all" not in source
    assert not hasattr(pi.PreparedStore, "delete_namespace")


# --- the real manifest through the adapter (fakes) ------------------------------------------------------------------------------------------

def test_the_ready_pages_of_the_real_manifest_hash_stably():
    manifest = load_manifest(SNAPSHOT)
    assert manifest_sha256(manifest) == manifest_sha256(load_manifest(SNAPSHOT))
    ready = [d.page_id for d in dispositions_for(manifest, today=date(2026, 10, 13)) if d.status == READY]
    assert len(ready) == 27


# --- a rehearsal on the real manifest, with a fake store ---------------------------------------------------------------------------------------

import socket  # noqa: E402

from app.services.education_page_dispositions import apply_review_overrides  # noqa: E402


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _synthetic(entry):
    """A prepared page shaped like a manifest entry (its size and url), without any real text."""
    n = entry["chunks"]
    return PreparedPage(id=entry["id"], canonical_url=entry["canonical_url"], title=entry["title"],
                        chunks=_chunks(n, entry["canonical_url"], entry["title"]), content_sha256=hashlib.sha256(entry["id"].encode()).hexdigest(),
                        tokens=entry["tokens"], category=entry["category"], country=entry["country"], kind=entry["kind"])


@pytest.mark.asyncio
async def test_rehearsal_only_the_27_ready_pages_go_in_and_the_four_old_guides_wait_for_their_reviewed_replacements():
    manifest = load_manifest(SNAPSHOT)
    entries = {p["id"]: p for p in manifest["pages"]}
    ordered = dispositions_for(manifest, today=date(2026, 10, 13))
    ready = [d for d in ordered if d.status == READY]
    assert len(ready) == 27

    # 1. the ready pages: ingested with a fake store, in source-backed-first order
    pages = [_synthetic(entries[d.page_id]) for d in ready]
    store = FakeStore()
    candidates = manifest["plan"]["retire_candidates"]
    old_ids = [c["job_id"] for c in candidates]
    assert len(old_ids) == 4
    for c in candidates:
        store.seed_job(c["job_id"], None, title="old thin guide", rows=1)
    dispositions = {d.page_id: d for d in ordered}
    approval = ExecutionApproval(manifest_sha256(manifest), "admizz-test", "rehearsal", tuple(sorted(p.id for p in pages)), tuple(old_ids))
    report = await run_prepared_ingestion(pages, store, manifest=manifest, dispositions=dispositions, target=TARGET, mode="execute", approval=approval)
    assert report.status == "completed" and report.all_verified and len(report.pages) == 27
    assert report.estimate["chunks"] == sum(len(p.chunks) for p in pages)
    first_classes = [entries[p.page_id]["content_class"] for p in report.pages]
    assert first_classes[:first_classes.count("source_backed")] == ["source_backed"] * first_classes.count("source_backed")

    # 2. the old guides cannot be retired: their replacements are the guides, which are still in review and were not ingested
    result = await retire_confirmed_jobs(store, report=report, candidates=candidates, approval=approval, retrieval_check=_ok, pages=pages, execute=True)
    assert result.status == "refused" and all(j in store.jobs for j in old_ids)

    # 3. a review page cannot be added without a named reviewer
    guides = [_synthetic(entries[c["page_id"]]) for c in candidates]
    refused = await run_prepared_ingestion(guides, store, manifest=manifest, dispositions=dispositions, target=TARGET)
    assert refused.status == "refused" and all("not ready" in p for p in refused.problems if "not ready" in p) and refused.problems

    # 4. after review the four guides can be ingested, and only then can the exact old jobs be planned for retirement
    reviewed, problems = apply_review_overrides(ordered, {g.id: {"status": "ready", "reviewed_by": "A. Reviewer",
                                                                  "reason": "university list reviewed and accepted"} for g in guides})
    assert problems == []
    all_pages = pages + guides
    approval2 = ExecutionApproval(manifest_sha256(manifest), "admizz-test", "rehearsal", tuple(sorted(p.id for p in all_pages)), tuple(old_ids))
    report2 = await run_prepared_ingestion(all_pages, store, manifest=manifest, dispositions={d.page_id: d for d in reviewed}, target=TARGET,
                                           mode="execute", approval=approval2)
    assert report2.status == "completed" and report2.all_verified and len(report2.pages) == 31
    assert [p.action for p in report2.pages].count("skipped_already_ingested") == 27           # the first 27 were recognised, not stored twice
    plan = await retire_confirmed_jobs(store, report=report2, candidates=candidates, approval=approval2, retrieval_check=_ok, pages=all_pages)
    assert plan.status == "planned" and [j["job_id"] for j in plan.jobs] == old_ids and not plan.executed
    assert all(j in store.jobs for j in old_ids)                                                # a plan deletes nothing
