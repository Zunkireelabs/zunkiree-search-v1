"""Prepared-pages ingestion for the Admizz website: plan, preflight, execute, retire. Prepared, tested, and NOT wired to anything.

This is the logic of a future, separately approved ingestion of already extracted pages into the `admizz-test` knowledge base. It
talks to the world only through a `PreparedStore` that the caller must hand in explicitly: there are no default clients, no
singletons and no database or network import in this module, so it cannot reach a real service by accident. The real store
(`education_prepared_store.py`) is a separate, equally explicit class, and no command in the repository runs either of them.

What it does, and what it deliberately does not do
  * Target lock: only the allow-listed tenant (`admizz-test`), whose customer record, site id and Pinecone namespace all agree.
  * Identity: a page's job id is derived from (tenant, canonical url, content hash). The existing pipeline is append-only (a new job
    and new vector ids on every run), so identity has to come from here: the same page and content always maps to the same job and
    vector ids, so a rerun recognises it instead of storing it twice. Changed content gets a new id and the older job for that url is
    reported for review, never deleted automatically.
  * Dry run is the default and only reads. Execution needs `mode="execute"`, a store with writes enabled, and an approval tied to the
    exact manifest, tenant and page list.
  * Postgres rows are committed before vectors are written, so a failure leaves rows without vectors. Nothing here claims the two
    stores are atomic: every page is written, then verified in BOTH stores, and a page that fails is cleaned up (its own job only) and
    the batch stops. A rerun resumes from what the store reports.
  * Retiring old jobs is a separate step that needs exact, confirmed job ids, a fully verified replacement run and a passing
    retrieval check; it deletes the job's vectors first and the job row second. There is no namespace-wide delete anywhere here.

Nothing here verifies website content: ingesting a page does not make its claims verified.
"""
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from app.services.education_ingest_plan import DEFAULT_MAX_TOKENS, PageWriteError, Plan, PlanPage, preflight
from app.services.education_page_dispositions import READY, Disposition
from app.services.education_sources import is_allowed_url
from app.utils.chunking import chunk_text

ALLOWED_TARGETS = frozenset({"admizz-test"})
_IDENTITY_NAMESPACE = uuid.UUID("7d4d3c35-5f0e-4b53-9d8c-2f0a5f3b9a11")
MAX_TITLE_CHARS = 255                      # IngestionJob.source_filename and DocumentChunk.source_title are String(255)
_OK_ACTIONS = ("added", "skipped_already_ingested", "recovered_and_added")


def source_job_id(site_id: str, canonical_url: str, content_sha256: str) -> uuid.UUID:
    """The deterministic job id of one version of one page of one tenant."""
    return uuid.uuid5(_IDENTITY_NAMESPACE, f"{site_id}|{canonical_url}|{content_sha256}")


# --- target ----------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Target:
    site_id: str
    customer_id: uuid.UUID
    namespace: str


@dataclass(frozen=True)
class TargetInfo:
    """What the store itself says it is connected to (a read), to be compared with the intended target."""
    site_id: str
    customer_id: uuid.UUID
    website_type: str
    namespace: str


def validate_target(target: Target, info: TargetInfo) -> list[str]:
    problems = []
    if target.site_id not in ALLOWED_TARGETS:
        problems.append(f"{target.site_id!r} is not an allowed target (allowed: {sorted(ALLOWED_TARGETS)})")
    if target.namespace != target.site_id:
        problems.append(f"namespace {target.namespace!r} must equal the site id {target.site_id!r}")
    if info.site_id != target.site_id:
        problems.append(f"the store's target site_id {info.site_id!r} does not match {target.site_id!r}")
    if info.customer_id != target.customer_id:
        problems.append("the store's customer id does not match the intended customer")
    if info.website_type != "education":
        problems.append(f"the tenant is {info.website_type!r}, not an education tenant")
    if info.namespace != target.namespace:
        problems.append(f"the store's vector namespace {info.namespace!r} does not match {target.namespace!r}")
    return problems


# --- pages and the store interface ------------------------------------------------------------------------------------------------

@dataclass
class PreparedPage:
    id: str
    canonical_url: str
    title: str
    chunks: list                    # dicts: content, chunk_index, token_count, source_url, source_title
    content_sha256: str
    tokens: int
    category: str | None = None
    country: str | None = None
    kind: str | None = None
    site_id: str = "admizz-test"

    @property
    def job_id(self) -> uuid.UUID:
        return source_job_id(self.site_id, self.canonical_url, self.content_sha256)


@dataclass
class JobState:
    job_id: str
    status: str
    source_url: str | None
    title: str | None
    chunks_expected: int
    rows: int
    vectors: int


@dataclass
class WriteResult:
    job_id: str
    rows: int
    vectors: int


@dataclass
class Verification:
    rows: int
    vectors: int


class PreparedStore(Protocol):
    writes_enabled: bool

    async def describe_target(self) -> TargetInfo: ...                          # read
    async def jobs_for_url(self, canonical_url: str) -> list[JobState]: ...     # read: every job of this tenant for the url
    async def write_page(self, page: PreparedPage) -> WriteResult: ...          # write: job + rows + vectors; PageWriteError on failure
    async def verify_job(self, job_id: str, expected_chunks: int) -> Verification: ...   # read: rows AND vectors actually present
    async def cleanup_job(self, job_id: str) -> None: ...                       # write: this adapter's own partial job
    async def job_vector_ids(self, job_id: str) -> list[str]: ...               # read
    async def delete_vectors(self, ids: list[str]) -> None: ...                 # write: exactly these ids
    async def delete_job(self, job_id: str) -> None: ...                        # write: exactly this job and, by cascade, its rows


def prepare_page(entry: dict, extracted, *, site_id: str = "admizz-test") -> PreparedPage:
    """A page ready to write: the extracted text split by the project's own chunker, every chunk carrying the canonical url and title,
    and a hash of the text for the page's deterministic identity. `extracted` is an `ExtractedPage`."""
    text = extracted.text
    if not text:
        raise ValueError(f"{entry.get('id')}: nothing was extracted, so there is nothing to store")
    url, title = entry["canonical_url"], (entry.get("title") or extracted.title or "").strip()
    chunks = chunk_text(text)
    for chunk in chunks:
        chunk["source_url"], chunk["source_title"] = url, title
    return PreparedPage(id=entry["id"], canonical_url=url, title=title, chunks=chunks, content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                        tokens=sum(c.get("token_count") or 0 for c in chunks), category=entry.get("category"), country=entry.get("country"),
                        kind=entry.get("kind"), site_id=site_id)


# --- approval --------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecutionApproval:
    manifest_sha256: str
    site_id: str
    approved_by: str
    page_ids: tuple
    confirmed_retire_job_ids: tuple = ()


def manifest_sha256(manifest: dict) -> str:
    """A hash of what an approval covers: the pages, their urls, sizes, classes and (when recorded) content hashes. Order-insensitive."""
    rows = sorted(({"id": p.get("id"), "canonical_url": p.get("canonical_url"), "chunks": p.get("chunks"), "tokens": p.get("tokens"),
                    "eligible": p.get("eligible_for_ingestion"), "class": p.get("content_class"), "content": p.get("content_sha256")}
                   for p in manifest.get("pages", [])), key=lambda r: str(r["id"]))
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def check_approval(approval: ExecutionApproval | None, manifest: dict, pages: list[PreparedPage], target: Target) -> list[str]:
    if approval is None:
        return ["execution needs an explicit approval"]
    problems = []
    if approval.manifest_sha256 != manifest_sha256(manifest):
        problems.append("the approval was given for a different manifest")
    if approval.site_id != target.site_id:
        problems.append(f"the approval is for {approval.site_id!r}, not {target.site_id!r}")
    if not str(approval.approved_by or "").strip():
        problems.append("the approval does not name who approved it")
    if tuple(sorted(approval.page_ids)) != tuple(sorted(p.id for p in pages)):
        problems.append("the approval covers different pages than the ones planned")
    return problems


# --- the run ----------------------------------------------------------------------------------------------------------------------

@dataclass
class PageResult:
    page_id: str
    state: str = ""
    action: str = ""
    job_id: str | None = None
    rows: int = 0
    vectors: int = 0
    error: str | None = None
    other_job_ids: list = field(default_factory=list)
    inconsistent_other_jobs: list = field(default_factory=list)


@dataclass
class RunReport:
    mode: str
    status: str = "dry_run"
    problems: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    estimate: dict = field(default_factory=dict)

    @property
    def all_verified(self) -> bool:
        return self.mode == "execute" and bool(self.pages) and all(p.action in _OK_ACTIONS for p in self.pages)


def _page_problems(pages: list[PreparedPage], manifest: dict, dispositions: dict[str, Disposition], target: Target,
                   max_tokens: int) -> tuple[list[str], dict]:
    problems: list[str] = []
    entries = {p.get("id"): p for p in manifest.get("pages", [])}
    for page in pages:
        if page.site_id != target.site_id:
            problems.append(f"{page.id}: prepared for {page.site_id!r}, not {target.site_id!r}")
        disposition = dispositions.get(page.id)
        if disposition is None:
            problems.append(f"{page.id}: no disposition")
        elif disposition.status != READY:
            problems.append(f"{page.id}: not ready for ingestion ({disposition.status})")
        if not 1 <= len(page.title or "") <= MAX_TITLE_CHARS:
            problems.append(f"{page.id}: title must be 1 to {MAX_TITLE_CHARS} characters")
        if not page.chunks:
            problems.append(f"{page.id}: no chunks to store")
        elif any(c.get("source_url") != page.canonical_url or c.get("source_title") != page.title for c in page.chunks):
            problems.append(f"{page.id}: chunk metadata does not carry the canonical url and title")
        entry = entries.get(page.id)
        if entry is None:
            problems.append(f"{page.id}: not in the manifest")
        else:
            stale = [k for k, mine in (("chunks", len(page.chunks)), ("tokens", page.tokens)) if entry.get(k) != mine]
            if entry.get("content_sha256") and entry["content_sha256"] != page.content_sha256:
                stale.append("content")
            if entry.get("canonical_url") != page.canonical_url:
                stale.append("url")
            if stale:
                problems.append(f"{page.id}: changed since the manifest ({', '.join(stale)})")
    plan = Plan(add=[PlanPage(id=p.id, canonical_url=p.canonical_url, title=p.title, chunks=len(p.chunks), tokens=p.tokens) for p in pages])
    plan_problems, estimate = preflight(plan, None, max_tokens=max_tokens)
    return problems + plan_problems, estimate


async def _classify(store: PreparedStore, page: PreparedPage) -> PageResult:
    result = PageResult(page.id, job_id=str(page.job_id))
    jobs = await store.jobs_for_url(page.canonical_url)
    own = [j for j in jobs if j.job_id == str(page.job_id)]
    others = [j for j in jobs if j.job_id != str(page.job_id)]
    result.other_job_ids = [j.job_id for j in others]
    result.inconsistent_other_jobs = [(j.job_id, j.rows, j.vectors) for j in others if j.rows != j.vectors]
    expected = len(page.chunks)
    if own:
        j = own[0]
        result.rows, result.vectors = j.rows, j.vectors
        done = j.status == "completed" and j.rows == expected and j.vectors == expected
        result.state = "already_ingested" if done else "incomplete_own_job"
    else:
        result.state = "ambiguous_same_url_different_content" if others else "new"
    return result


async def _write_and_verify(store: PreparedStore, page: PreparedPage, result: PageResult, action: str) -> bool:
    expected, job_id = len(page.chunks), str(page.job_id)
    try:
        written = await store.write_page(page)
        job_id = written.job_id
        found = await store.verify_job(job_id, expected)
        if found.rows != expected or found.vectors != expected:
            raise PageWriteError(f"verification failed: expected {expected} rows and {expected} vectors, found {found.rows} and {found.vectors}", job_id)
        result.action, result.job_id, result.rows, result.vectors = action, job_id, found.rows, found.vectors
        return True
    except Exception as error:
        job_id = getattr(error, "job_id", None) or job_id
        result.action, result.error = "failed", str(error)
        try:
            await store.cleanup_job(job_id)        # this adapter's own half-written job, so a rerun starts clean
        except Exception as cleanup_error:
            result.error += f"; cleanup failed: {cleanup_error}"
        return False


async def run_prepared_ingestion(pages: list[PreparedPage], store: PreparedStore, *, manifest: dict, dispositions: dict[str, Disposition],
                                 target: Target, mode: str = "dry_run", approval: ExecutionApproval | None = None, resume: bool = False,
                                 order: list[str] | None = None, max_tokens: int = DEFAULT_MAX_TOKENS) -> RunReport:
    report = RunReport(mode=mode)
    if mode not in ("dry_run", "execute"):
        report.status, report.problems = "refused", [f"unknown mode {mode!r}"]
        return report
    ranking = order or [i for i in dispositions if i in {p.id for p in pages}] or [p.id for p in pages]
    pages = sorted(pages, key=lambda p: ranking.index(p.id) if p.id in ranking else len(ranking))

    problems, report.estimate = _page_problems(pages, manifest, dispositions, target, max_tokens)
    if not problems:
        problems += validate_target(target, await store.describe_target())
    if mode == "execute":
        problems += check_approval(approval, manifest, pages, target)
        if not getattr(store, "writes_enabled", False):
            problems.append("the store has writes disabled")
    if problems:
        report.status, report.problems = "refused", problems
        return report

    stopped = review = False
    for page in pages:
        result = await _classify(store, page)
        report.pages.append(result)
        if mode == "dry_run":
            result.action = {"new": "would_add", "already_ingested": "would_skip_already_ingested",
                             "incomplete_own_job": "needs_recovery", "ambiguous_same_url_different_content": "needs_review"}[result.state]
            continue
        if result.state == "already_ingested":
            result.action = "skipped_already_ingested"
        elif result.state == "ambiguous_same_url_different_content":
            result.action, review = "needs_review", True          # reported, never skipped silently, never touched; the others go on
        elif result.state == "incomplete_own_job" and not resume:
            result.action, stopped = "needs_recovery", True
            break
        elif result.state == "incomplete_own_job":
            try:
                await store.cleanup_job(str(page.job_id))
            except Exception as error:
                result.action, result.error, stopped = "failed", f"cleanup failed: {error}", True
                break
            if not await _write_and_verify(store, page, result, "recovered_and_added"):
                stopped = True
                break
        elif not await _write_and_verify(store, page, result, "added"):
            stopped = True
            break
    report.status = "dry_run" if mode == "dry_run" else "stopped" if stopped else "completed_with_review_items" if review else "completed"
    return report


# --- retiring old jobs (planned, never automatic) ---------------------------------------------------------------------------------

@dataclass
class RetirementReport:
    status: str = "planned"          # planned | retired | refused | stopped
    problems: list = field(default_factory=list)
    jobs: list = field(default_factory=list)       # [{"job_id", "vector_ids"}] exactly what would be / was deleted
    retired: list = field(default_factory=list)
    executed: bool = False


async def retire_confirmed_jobs(store: PreparedStore, *, report: RunReport, candidates: list[dict], approval: ExecutionApproval,
                                retrieval_check: Callable[[PreparedPage], Awaitable[bool]] | None, pages: list[PreparedPage],
                                execute: bool = False) -> RetirementReport:
    """Plan, or with execute=True carry out, the retirement of OLD jobs, and only these exact, confirmed ids.

    Refused unless the replacement run was an executed run in which every page is verified, the ids are confirmed in the approval and
    are retirement candidates, and a retrieval check passes for each replacement page. Old jobs are deleted vectors first, row second."""
    out = RetirementReport()
    known = {c["job_id"]: c for c in candidates}
    verified = {p.page_id for p in report.pages if p.action in _OK_ACTIONS}
    by_id = {p.id: p for p in pages}
    if not report.all_verified:
        out.problems.append("the replacement pages are not all verified in an executed run")
    if approval.site_id not in ALLOWED_TARGETS:
        out.problems.append(f"{approval.site_id!r} is not an allowed target")
    if not approval.confirmed_retire_job_ids:
        out.problems.append("no job ids were confirmed for retirement")
    if not set(approval.page_ids) <= verified:
        out.problems.append("the approval covers pages that are not verified in this run")
    if retrieval_check is None:
        out.problems.append("a retrieval check is required before any old job is retired")
    for job_id in approval.confirmed_retire_job_ids:
        candidate = known.get(job_id)
        if candidate is None:
            out.problems.append(f"job id {job_id!r} is not a retirement candidate (exact, confirmed ids only)")
        elif candidate["page_id"] not in verified:
            out.problems.append(f"job {job_id}: its replacement page {candidate['page_id']!r} is not verified in this run")
        elif retrieval_check is not None:
            page = by_id.get(candidate["page_id"])
            try:
                passed = page is not None and bool(await retrieval_check(page))
            except Exception:
                passed = False
            if not passed:
                out.problems.append(f"job {job_id}: the retrieval check failed for {candidate['page_id']!r}")
    if execute and not getattr(store, "writes_enabled", False):
        out.problems.append("the store has writes disabled")
    if out.problems:
        out.status = "refused"
        return out

    out.jobs = [{"job_id": job_id, "vector_ids": await store.job_vector_ids(job_id)} for job_id in approval.confirmed_retire_job_ids]
    if not execute:
        return out
    out.executed = True
    for job in out.jobs:
        try:
            await store.delete_vectors(job["vector_ids"])         # vectors first: a failure leaves stale rows, never orphan vectors
            await store.delete_job(job["job_id"])
        except Exception as error:
            out.status = "stopped"
            out.problems.append(f"job {job['job_id']}: {error}")
            return out
        out.retired.append(job["job_id"])
    out.status = "retired"
    return out
