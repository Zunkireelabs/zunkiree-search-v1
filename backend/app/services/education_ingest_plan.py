"""How a safe ingestion of the Admizz pages would run: decisions only, no I/O.

This module decides WHAT to store and in WHAT ORDER; a `Store` (Supabase + Pinecone, in a future task that needs explicit
approval) does the writing. Everything here is tested against an in-memory fake store, so no database, vector store, embeddings
service or network is involved.

What the existing ingestion service does (verified in `IngestionService._process_chunks`), and what follows from it:
  * It is append-only: every run creates a new job and vector ids are `<job id>_<n>`. Ingesting a page twice stores it twice, and
    there is no unique key on the source. So idempotency has to come from here: a page whose canonical url is already stored by a
    completed job is skipped.
  * Postgres rows are committed BEFORE the vectors are upserted. A failure in between leaves rows with no vectors (found by
    `find_inconsistent_jobs`, cleaned by retiring that job); it can never leave vectors with no rows.
  * Retrieval cannot tell old chunks from new ones, so replacing means: add and verify the new pages first (a short period in
    which both exist), and only then retire the old jobs. Retiring deletes the job's vectors first and its rows second, so a
    failure leaves stale rows (harmless, retryable), never orphan vectors.
  * Old chunks are only ever retired by an explicit, confirmed job id. A matching title is NOT proof of the same source.

Nothing here verifies website content; every class below is an unreviewed class.
"""
import math
import re
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit

from app.services.education_sources import is_allowed_url

# ASSUMPTION, not a quoted price: text-embedding-3-large (the project's EMBEDDING_MODEL) at about this many US dollars per million
# input tokens. Check current OpenAI pricing before relying on the dollar figure; the token and call counts are exact.
EMBEDDING_PRICE_PER_MILLION = 0.13
EMBEDDING_BATCH_SIZE = 100          # IngestionService._process_chunks requests embeddings 100 chunks at a time
DEFAULT_MAX_TOKENS = 500_000        # a preflight guard: a plan bigger than this is refused

# Pages that exist to be LINKED (a sign-up form, a contact page), not to be read by the knowledge base.
LINK_ONLY_CATEGORIES = ("contact",)

_OFFICIAL_SUFFIXES = (".gov", ".gov.uk", ".gov.au", ".govt.nz", ".gc.ca", ".europa.eu")
_OFFICIAL_HOSTS = ("canada.ca",)


def _is_official(url: str) -> bool:
    host = (urlsplit(url or "").hostname or "").lower()
    return host.endswith(_OFFICIAL_SUFFIXES) or any(host == h or host.endswith("." + h) for h in _OFFICIAL_HOSTS)


def classify_content(*, has_checked_statement: bool = False, references=(), published: str | None = None,
                     checked: str | None = None) -> str:
    """How a page presents itself. Never 'verified': that is a human review, not something extraction can establish.

    source_backed: states when it was checked AND cites an official government source
    dated:         states a publication or checked date, without an official source
    explanatory:   neither (including a page that links an official source but states no date)"""
    stated = has_checked_statement or bool(checked)
    if stated and any(_is_official(r.get("url", "")) for r in references):
        return "source_backed"
    if stated or published:
        return "dated"
    return "explanatory"


# --- what is already stored ----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ExistingSource:
    job_id: str
    source_type: str
    source_url: str | None
    title: str
    chunks: int
    characters: int
    tokens: int

    @classmethod
    def from_snapshot(cls, row: dict) -> "ExistingSource":
        """A row of the read-only snapshot of ingestion jobs (job_id, source_type, urls, source_filename/title, chunk counts)."""
        return cls(job_id=str(row["job_id"]), source_type=row.get("source_type") or "",
                   source_url=row.get("job_source_url") or row.get("chunk_source_url") or None,
                   title=row.get("source_title") or row.get("job_source_filename") or "",
                   chunks=int(row.get("chunks") or 0), characters=int(row.get("chars") or 0), tokens=int(row.get("tokens") or 0))


def _norm_title(title: str) -> str:
    title = re.sub(r"\s*[-|–—]\s*admizz education\s*$", "", (title or "").strip(), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", title).strip().lower()


def find_overlap(url: str, title: str, existing: list[ExistingSource]) -> dict | None:
    """Whether a stored source may be the same page. Only an identical url is proof; a title match is reported as exactly that."""
    for e in existing:
        if e.source_url and e.source_url == url:
            return {"match": "url", "job_id": e.job_id, "job_ids": [x.job_id for x in existing if x.source_url == url],
                    "existing_title": e.title, "existing_characters": e.characters, "proof": "same_url"}
    wanted = _norm_title(title)
    same = [e for e in existing if wanted and _norm_title(e.title) == wanted]
    if same:
        return {"match": "title", "job_id": same[0].job_id, "job_ids": [e.job_id for e in same], "existing_title": same[0].title,
                "existing_characters": same[0].characters, "proof": "title_only_not_proven_same_source"}
    return None


# --- cost ----------------------------------------------------------------------------------------------------------------

def _estimate(chunks: int, tokens: int, price_per_million: float, batch_size: int) -> dict:
    return {"chunks": chunks, "tokens": tokens, "api_calls": math.ceil(chunks / batch_size) if chunks else 0,
            "usd": tokens * price_per_million / 1_000_000,
            "note": (f"Assumption: about ${price_per_million} per million input tokens for the embedding model and batches of "
                     f"{batch_size} chunks; check current pricing. Tokens and calls come from the chunk manifest.")}


def estimate_embeddings(chunk_tokens: list[int], *, price_per_million: float = EMBEDDING_PRICE_PER_MILLION,
                        batch_size: int = EMBEDDING_BATCH_SIZE) -> dict:
    return _estimate(len(chunk_tokens), sum(chunk_tokens), price_per_million, batch_size)


# --- the plan ------------------------------------------------------------------------------------------------------------

@dataclass
class PlanPage:
    id: str
    canonical_url: str
    title: str
    chunks: int
    tokens: int
    warnings: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    category: str | None = None


@dataclass
class AddResult:
    job_id: str
    chunks: int


@dataclass
class Plan:
    add: list = field(default_factory=list)
    skip: list = field(default_factory=list)
    retire: list = field(default_factory=list)                  # job ids an operator confirmed for retirement
    retire_candidates: list = field(default_factory=list)       # job ids that MAY be replaced, for the operator to decide
    ignored_confirmations: list = field(default_factory=list)


def plan_ingestion(pages: list[PlanPage], existing: list[ExistingSource], confirm_retire=frozenset()) -> Plan:
    plan = Plan()
    candidates: dict[str, dict] = {}
    for page in pages:
        if page.category in LINK_ONLY_CATEGORIES:
            plan.skip.append({"page_id": page.id, "reason": "link_only_category"})
            continue
        if page.chunks <= 0:
            plan.skip.append({"page_id": page.id, "reason": "no_content"})
            continue
        overlap = find_overlap(page.canonical_url, page.title, existing)
        if overlap and overlap["match"] == "url":
            plan.skip.append({"page_id": page.id, "reason": "already_ingested_same_url"})
            continue
        plan.add.append(page)
        if overlap:
            for job_id in overlap["job_ids"]:
                candidates.setdefault(job_id, {"job_id": job_id, "page_id": page.id, "proof": overlap["proof"]})
    plan.retire_candidates = list(candidates.values())
    plan.retire = [c["job_id"] for c in plan.retire_candidates if c["job_id"] in confirm_retire]
    plan.ignored_confirmations = sorted(set(confirm_retire) - set(plan.retire))
    return plan


def preflight(plan: Plan, existing: list[ExistingSource] | None, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> tuple[list[str], dict]:
    """(problems, cost estimate). A plan with any problem must not be executed. `existing` None skips the retire-id check."""
    problems: list[str] = []
    if not plan.add:
        problems.append("nothing to add")
    seen: set[str] = set()
    for page in plan.add:
        if not is_allowed_url(page.canonical_url):
            problems.append(f"{page.id}: {page.canonical_url!r} is not an approved Admizz url")
        if page.canonical_url in seen:
            problems.append(f"{page.id}: duplicate canonical url {page.canonical_url}")
        seen.add(page.canonical_url)
    if existing is not None:
        known = {e.job_id for e in existing}
        problems += [f"{job_id} is not an existing job" for job_id in plan.retire if job_id not in known]
    estimate = _estimate(sum(p.chunks for p in plan.add), sum(p.tokens for p in plan.add), EMBEDDING_PRICE_PER_MILLION, EMBEDDING_BATCH_SIZE)
    if estimate["tokens"] > max_tokens:
        problems.append(f"estimated {estimate['tokens']} tokens exceed the budget of {max_tokens}")
    return problems, estimate


# --- execution (through a store) -----------------------------------------------------------------------------------------

class PageWriteError(Exception):
    """A store raises this when a page's write fails part way; `job_id` names what it had already created so it can be cleaned."""

    def __init__(self, message: str, job_id: str | None = None):
        super().__init__(message)
        self.job_id = job_id


class Store(Protocol):
    async def completed_urls(self) -> set[str]: ...          # canonical urls of pages stored by completed, verified jobs
    async def add_page(self, page: PlanPage) -> AddResult: ...
    async def verify_page(self, job_id: str, expected_chunks: int) -> bool: ...   # rows AND vectors both present
    async def retire_job(self, job_id: str) -> None: ...     # vectors first, then rows


@dataclass
class RunLog:
    status: str = "completed"       # completed | completed_with_failures | stopped | refused
    pages: list = field(default_factory=list)
    retired: list = field(default_factory=list)
    problems: list = field(default_factory=list)


async def execute_plan(plan: Plan, store: Store, *, stop_on_error: bool = True) -> RunLog:
    log = RunLog()
    log.problems, _ = preflight(plan, None)
    if log.problems:
        log.status = "refused"
        return log
    done = await store.completed_urls()
    failed = False
    for page in plan.add:
        if page.canonical_url in done:
            log.pages.append({"page_id": page.id, "status": "skipped_already_ingested"})
            continue
        job_id = None
        try:
            result = await store.add_page(page)
            job_id = result.job_id
            if not await store.verify_page(job_id, page.chunks):
                raise PageWriteError(f"verification failed: expected {page.chunks} chunks in both stores", job_id)
            log.pages.append({"page_id": page.id, "status": "added", "job_id": job_id})
        except Exception as error:
            failed = True
            job_id = getattr(error, "job_id", None) or job_id
            entry = {"page_id": page.id, "status": "failed", "error": str(error)}
            if job_id:
                try:
                    await store.retire_job(job_id)           # remove the half-written page so a rerun starts clean
                except Exception as cleanup_error:
                    entry["cleanup_error"] = str(cleanup_error)
            log.pages.append(entry)
            if stop_on_error:
                log.status = "stopped"
                return log
    if failed:
        log.status = "completed_with_failures"
        return log                                            # nothing old is retired unless every new page is in and verified
    for job_id in plan.retire:
        await store.retire_job(job_id)
        log.retired.append(job_id)
    return log


def find_inconsistent_jobs(row_counts: dict[str, int], vector_counts: dict[str, int]) -> list[tuple[str, int, int]]:
    """(job id, postgres rows, vectors) for every job whose two stores disagree: the signature of a half-written ingestion."""
    return [(job, row_counts.get(job, 0), vector_counts.get(job, 0)) for job in sorted(set(row_counts) | set(vector_counts))
            if row_counts.get(job, 0) != vector_counts.get(job, 0)]
