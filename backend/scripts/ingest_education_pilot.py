"""
GATED pilot ingestion of the best Admizz pages into the `admizz-test` knowledge base: plan, preflight, execute.

    plan       no website request, no database, no search index: lists the pilot pages, the manifest hash an approval must carry,
               the embedding volume and the approval template.
    preflight  fetches the pilot pages politely and READS the store (nothing is written) to say what is new, already stored or ambiguous.
    execute    needs --approval-file. Fetches, writes each page through the existing chunk pipeline, verifies BOTH stores, then checks that
               the chatbot's retrieval FINDS each page for realistic questions. It never retires or deletes anything.
    rollback   undoes a run: needs the run's --report and an --approval-file naming the exact job ids (confirmed_retire_job_ids) to remove.
               It removes only jobs that report shows the run ADDED (vectors first, then the job), and nothing else.

The pilot is the pages that are `ready` AND `source_backed` in a FRESH manifest (made by `python -m scripts.ingest_education_sources
--manifest FILE`, which records a content hash per page). An approval is a small JSON file naming the approver, the tenant, the exact page
ids and the manifest's SHA-256; changing any page invalidates it. Only `admizz-test` can be targeted. Real services are built inside
`real_services()` only, after every refusal check has passed.

Exit codes: 0 done; 1 refused or bad input; 2 plan/preflight problems; 3 ingestion (or rollback) stopped or failed; 4 stored but retrieval did not confirm.
Usage (from backend/): see docs/generative-ui/ADMIZZ-INGESTION-RUNBOOK.md
"""
import argparse
import asyncio
import json
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urljoin

from app.services.education_ingest_plan import DEFAULT_MAX_TOKENS, estimate_totals
from app.services.education_page_dispositions import READY, dispositions_for, load_manifest
from app.services.education_page_extractor import extract_page
from app.services.education_prepared_ingest import (
    ALLOWED_TARGETS, ExecutionApproval, Target, check_approval, manifest_sha256, prepare_page, run_prepared_ingestion,
)
from app.services.education_retrieval_check import load_probes, make_retrieval_check, pilot_probe_problems
from app.services.education_sources import SOURCES_DIR, is_allowed_url
from scripts.ingest_education_sources import (
    MAX_BYTES, MAX_REDIRECTS, USER_AGENT, FetchError, FetchTimeout, HttpxFetcher, Pacer, _canonical, _load_robots,
)

OK_ACTIONS = ("added", "skipped_already_ingested", "recovered_and_added")


def out(text: str = "") -> None:
    print(text)


# --- real services: the only place they are built --------------------------------------------------------------------------------

@asynccontextmanager
async def real_services(site_id: str, *, writes: bool):
    """A store (writes only if `writes`), the target and a retrieval function, on the REAL database and search index. Never called by a test."""
    from sqlalchemy import select

    from app.database import async_session_maker
    from app.models.customer import Customer
    from app.services.education_prepared_store import SqlPineconeStore
    from app.services.ingestion import IngestionService
    from app.services.query import get_query_service
    from app.services.vector_store import get_vector_store_service

    async with async_session_maker() as db:
        customer = (await db.execute(select(Customer).where(Customer.site_id == site_id, Customer.is_active == True))).scalar_one_or_none()  # noqa: E712
        if customer is None:
            raise SystemExit(f"no active customer with site_id {site_id!r}")
        target = Target(site_id=site_id, customer_id=customer.id, namespace=site_id)
        store = SqlPineconeStore(db=db, ingestion_service=IngestionService(), vector_store=get_vector_store_service(), target=target,
                                 allow_real_writes=writes)
        query_service = get_query_service()

        async def retrieve(question: str) -> list:
            result = await query_service._retrieve_and_rank(db=db, customer=customer, config=None, site_id=site_id, question=question, skip_rerank=True)
            return result.get("chunks_for_llm") or []

        yield SimpleNamespace(store=store, target=target, retrieve=retrieve)


# --- reading the website, politely -------------------------------------------------------------------------------------------------

def fetch_html(url: str, fetcher, pacer, robots) -> tuple[str | None, str | None, str | None]:
    """(html, final url, None) or (None, None, reason). Every hop: approved host, robots.txt, at most 1 request/second, bounded size, HTML only."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        if not robots.can_fetch(USER_AGENT, current):
            return None, None, "robots"
        pacer.wait()
        try:
            response = fetcher.fetch(current)
        except FetchTimeout:
            return None, None, "timeout"
        except FetchError:
            return None, None, "error"
        if response.status in (301, 302, 303, 307, 308):
            target = urljoin(current, response.location) if response.location else ""
            if not is_allowed_url(target):
                return None, None, "redirect_host"
            current = target
            continue
        if response.status != 200:
            return None, None, f"http_{response.status}"
        if response.headers.get("content-type", "").split(";")[0].strip().lower() != "text/html":
            return None, None, "content_type"
        if len(response.body) > MAX_BYTES:
            return None, None, "too_large"
        return response.body.decode("utf-8", "replace"), current, None
    return None, None, "too_many_redirects"


# --- the pilot ------------------------------------------------------------------------------------------------------------------------------------

def select_pilot(manifest: dict, dispositions: list, only: list[str]) -> tuple[list[str], list[str]]:
    """(ids, problems): the pages that are ready AND source-backed, optionally narrowed with --only; a page outside that set is refused."""
    classes = {p["id"]: p.get("content_class") for p in manifest["pages"]}
    pilot = [d.page_id for d in dispositions if d.status == READY and classes.get(d.page_id) == "source_backed"]
    if not only:
        return pilot, ([] if pilot else ["the manifest has no ready, source-backed page"])
    problems = [f"{i}: not a pilot page (it must be ready and source-backed in the manifest)" for i in only if i not in pilot]
    return [i for i in pilot if i in only], problems


def load_approval(path: Path) -> ExecutionApproval:
    try:
        doc = json.loads(Path(path).read_text())
        retire = tuple(doc.get("confirmed_retire_job_ids") or ())
        if not (isinstance(doc.get("manifest_sha256"), str) and isinstance(doc.get("site_id"), str) and isinstance(doc.get("approved_by"), str)
                and isinstance(doc.get("page_ids"), list) and all(isinstance(i, str) for i in doc["page_ids"])):
            raise ValueError("expected manifest_sha256, site_id, approved_by (strings) and page_ids (a list of ids)")
        return ExecutionApproval(manifest_sha256=doc["manifest_sha256"], site_id=doc["site_id"], approved_by=doc["approved_by"],
                                 page_ids=tuple(doc["page_ids"]), confirmed_retire_job_ids=retire)
    except (OSError, ValueError, AttributeError, TypeError) as e:
        raise ValueError(f"approval file unusable: {e}") from e


def print_plan(manifest: dict, entries: list[dict], probes: dict, problems: list[str], missing_hashes: list[str]) -> None:
    out(f"pilot pages ({len(entries)}): ready and source-backed, in ingestion order")
    for e in entries:
        out(f"  {e['id']:<22} {e['chunks']:>3} chunks {e['tokens']:>6} tokens  {e['canonical_url']}")
    est = estimate_totals(sum(e["chunks"] for e in entries), sum(e["tokens"] for e in entries))
    out(f"estimated embedding volume: {est['chunks']} chunks, {est['tokens']} tokens, {est['api_calls']} call(s), about ${est['usd']:.4f}")
    out(f"  {est['note']}")
    for problem in problems:
        out(f"  ! {problem}")
    if missing_hashes:
        out(f"  ! no content hash in the manifest for: {', '.join(missing_hashes)}. Preflight and execute need a manifest with content hashes: "
            "regenerate it with `python -m scripts.ingest_education_sources --manifest FILE`.")
    out()
    out("approval file to create after you have reviewed this (a person fills in approved_by; nothing runs without it):")
    out(json.dumps({"manifest_sha256": manifest_sha256(manifest), "site_id": "admizz-test", "approved_by": "<name of the person approving>",
                    "page_ids": sorted(e["id"] for e in entries)}, indent=2))


def print_report(report) -> None:
    out(f"ingestion: {report.status} (mode {report.mode})")
    for problem in report.problems:
        out(f"  ! {problem}")
    for p in report.pages:
        extra = f"  [{p.error}]" if p.error else ""
        out(f"  {p.page_id:<22} {p.state:<38} {p.action:<26} rows {p.rows} vectors {p.vectors}{extra}")
        if p.other_job_ids:
            out(f"      other jobs for the same url (left untouched): {', '.join(p.other_job_ids)}")


def report_json(report, checks, pages: dict, manifest_hash: str, site_id: str) -> dict:
    def page(p):
        prepared = pages.get(p.page_id)
        return {"page_id": p.page_id, "state": p.state, "action": p.action, "job_id": p.job_id, "rows": p.rows, "vectors": p.vectors, "error": p.error,
                "other_job_ids": p.other_job_ids, "canonical_url": prepared.canonical_url if prepared else None, "chunks": len(prepared.chunks) if prepared else 0}
    return {"manifest_sha256": manifest_hash, "site_id": site_id,
            "ingestion": {"mode": report.mode, "status": report.status, "problems": report.problems,
                          "estimate": {k: v for k, v in report.estimate.items() if k != "note"}, "pages": [page(p) for p in report.pages]},
            "retrieval": [{"page_id": c.page_id, "passed": c.passed, "results": [{"question": r.question, "found": r.found, "rank": r.rank,
                                                                                   "top_sources": r.top_sources, "error": r.error} for r in c.results]} for c in checks]}


async def rollback(args, real_factory) -> int:
    """Remove exactly the jobs a run added, named one by one in the approval. Never anything else; safe to repeat."""
    if args.site not in ALLOWED_TARGETS:
        out(f"refused: {args.site!r} is not an allowed target (allowed: {sorted(ALLOWED_TARGETS)})")
        return 1
    if not args.report or not args.approval_file:
        out("refused: rollback needs --report (the report of the run to undo) and --approval-file")
        return 1
    try:
        doc = json.loads(Path(args.report).read_text())
        run_pages = doc["ingestion"]["pages"]
        approval = load_approval(args.approval_file)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        out(f"refused: report or approval unusable: {e}")
        return 1
    added = {p["job_id"]: p for p in run_pages if p.get("action") in ("added", "recovered_and_added") and p.get("job_id")}
    ids = list(approval.confirmed_retire_job_ids)
    issues = []
    if approval.site_id != args.site:
        issues.append(f"the approval is for {approval.site_id!r}, not {args.site!r}")
    if not approval.approved_by.strip():
        issues.append("the approval does not name who approved it")
    if approval.manifest_sha256 != doc.get("manifest_sha256"):
        issues.append("the approval was given for a different run")
    if not ids:
        issues.append("no job ids were confirmed for rollback (confirmed_retire_job_ids)")
    issues += [f"job id {i!r} is not a page this run added (exact ids only)" for i in ids if i not in added]
    if issues:
        for issue in issues:
            out(f"refused: {issue}")
        return 1
    async with real_factory(args.site, writes=True) as real:
        for job_id in ids:
            page = added[job_id]
            if not any(s.job_id == job_id for s in await real.store.jobs_for_url(page["canonical_url"])):
                out(f"  {page['page_id']:<22} already removed")
                continue
            try:
                await real.store.cleanup_job(job_id)                      # vectors first, then the job and its rows
                left = await real.store.verify_job(job_id, page["chunks"])
                if left.rows or left.vectors:
                    raise RuntimeError(f"still {left.rows} rows and {left.vectors} vectors after removal")
            except Exception as error:
                out(f"  {page['page_id']:<22} FAILED to remove ({error}); stopping, nothing else was touched")
                return 3
            out(f"  {page['page_id']:<22} removed (job {job_id})")
    out("rollback finished: only the confirmed jobs of that run were removed.")
    return 0


async def run(args, *, fetcher, real_factory, clock, sleep, today: date) -> int:
    if args.site not in ALLOWED_TARGETS:
        out(f"refused: {args.site!r} is not an allowed target (allowed: {sorted(ALLOWED_TARGETS)})")
        return 1
    try:
        manifest = load_manifest(args.manifest)
        probes = load_probes(args.probes or SOURCES_DIR / f"{args.site}.probes.json")
    except ValueError as e:
        out(f"refused: {e}")
        return 1
    dispositions = dispositions_for(manifest, today=today)
    ids, problems = select_pilot(manifest, dispositions, args.only)
    entries = {p["id"]: p for p in manifest["pages"]}
    chosen = [entries[i] for i in ids]
    missing_hashes = [e["id"] for e in chosen if not e.get("content_sha256")]
    problems += pilot_probe_problems([SimpleNamespace(id=e["id"]) for e in chosen], probes)

    if args.mode == "plan":
        print_plan(manifest, chosen, probes, problems, missing_hashes)
        return 0
    if problems or missing_hashes:
        for problem in problems:
            out(f"refused: {problem}")
        if missing_hashes:
            out(f"refused: no content hash in the manifest for {', '.join(missing_hashes)}; regenerate it with scripts.ingest_education_sources --manifest")
        return 1

    approval = None
    if args.mode == "execute":
        if not args.approval_file:
            out("refused: execute needs --approval-file (run `plan` for the template)")
            return 1
        try:
            approval = load_approval(args.approval_file)
        except ValueError as e:
            out(f"refused: {e}")
            return 1
        issues = check_approval(approval, manifest, [SimpleNamespace(id=i) for i in ids], Target(args.site, uuid.UUID(int=0), args.site))
        if approval.confirmed_retire_job_ids:
            issues.append("this command never retires old jobs; retirement is a separate, later step (remove confirmed_retire_job_ids)")
        if issues:
            for issue in issues:
                out(f"refused: {issue}")
            return 1

    # the website: polite, bounded, approved host only
    pacer = Pacer(clock, sleep)
    fetcher = fetcher or HttpxFetcher()
    robots = _load_robots(fetcher, pacer)
    if robots is None:
        out("refused: robots.txt could not be read, so nothing is fetched")
        return 1
    pages, fetch_problems = [], []
    for e in chosen:
        html, final_url, reason = fetch_html(e["canonical_url"], fetcher, pacer, robots)
        if reason:
            fetch_problems.append(f"{e['id']}: could not be fetched ({reason})")
            continue
        if _canonical(html, final_url) != e["canonical_url"]:
            fetch_problems.append(f"{e['id']}: its canonical url is now {_canonical(html, final_url)}, the manifest says {e['canonical_url']}")
            continue
        try:
            pages.append(prepare_page(e, extract_page(html), site_id=args.site))
        except ValueError as error:
            fetch_problems.append(str(error))
    if fetch_problems:
        for problem in fetch_problems:
            out(f"refused: {problem}")
        return 1

    writes = args.mode == "execute"
    async with real_factory(args.site, writes=writes) as real:
        report = await run_prepared_ingestion(pages, real.store, manifest=manifest, dispositions={d.page_id: d for d in dispositions}, target=real.target,
                                              mode="execute" if writes else "dry_run", approval=approval, resume=args.resume, order=ids,
                                              max_tokens=args.max_tokens)
        print_report(report)
        checks = []
        code = 0
        if report.status == "refused":
            code = 2
        elif args.mode == "execute":
            if report.status != "completed" or not report.all_verified:
                out("not everything was stored and verified: fix the cause and run the same command again (finished pages are skipped).")
                code = 3
            else:
                hook = make_retrieval_check(real.retrieve, probes)
                for page in pages:
                    await hook(page)
                checks = hook.checks
                out("retrieval: does the chatbot find each page for realistic questions?")
                for c in checks:
                    out(f"  {c.page_id:<22} {'FOUND' if c.passed else 'NOT FOUND'}")
                    for r in c.results:
                        verdict = f"found (rank {r.rank})" if r.found else f"not found{f' [{r.error}]' if r.error else ''}; top results: {', '.join(r.top_sources) or 'none'}"
                        out(f"      {verdict}  <- {r.question}")
                if not all(c.passed for c in checks):
                    out("Do NOT retire any old job: retrieval did not confirm every page. Read the lines above, fix, then check again.")
                    code = 4
                else:
                    out("every probe question found its page. A person should still read the answers before any old job is retired.")
        if args.report:
            Path(args.report).write_text(json.dumps(report_json(report, checks, {p.id: p for p in pages}, manifest_sha256(manifest), args.site),
                                                    indent=2, ensure_ascii=False) + "\n")
        return code


def main(argv: list[str] | None = None, *, fetcher=None, real_factory=None, clock=time.monotonic, sleep=time.sleep, today: date | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["plan", "preflight", "execute", "rollback"])
    parser.add_argument("--manifest", type=Path, help="plan/preflight/execute: a fresh manifest from scripts.ingest_education_sources --manifest")
    parser.add_argument("--probes", type=Path, help="probe questions (default: app/data/education_sources/<site>.probes.json)")
    parser.add_argument("--site", default="admizz-test", help="only admizz-test is allowed")
    parser.add_argument("--only", action="append", default=[], help="narrow the pilot to this page id (repeatable)")
    parser.add_argument("--approval-file", type=Path, help="execute only: the approval JSON")
    parser.add_argument("--resume", action="store_true", help="execute only: clean and rewrite a page a crashed run left half-written")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help="refuse a plan larger than this many embedding tokens")
    parser.add_argument("--report", type=Path, help="execute: write a JSON report (no page text). rollback: the report of the run to undo")
    args = parser.parse_args(argv)
    if args.mode != "rollback" and not args.manifest:
        parser.error("--manifest is required for plan, preflight and execute")
    if args.mode == "rollback":
        return asyncio.run(rollback(args, real_factory or real_services))
    return asyncio.run(run(args, fetcher=fetcher, real_factory=real_factory or real_services, clock=clock, sleep=sleep, today=today or date.today()))


if __name__ == "__main__":
    sys.exit(main())
