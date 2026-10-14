"""
DRY RUN of an ingestion of the education source registry (app/data/education_sources/<site_id>.json).

Fetches the registry's pages politely, extracts their text with the Admizz page extractor
(app/services/education_page_extractor.py) and splits it into the chunks a real ingestion WOULD store, then prints a report and,
with --manifest, writes a JSON manifest of every page. It writes NOTHING to any store: no database, no vector store, no embeddings call (those cost money and change shared data),
and it never rewrites the registry (ingested_at stays as it is). The pages are public, unverified website content; this tool
does not make them verified and nothing it produces is catalog data.

Rules it follows:
  * only urls listed in the registry, https, on the approved host; every redirect hop is checked the same way
  * robots.txt is honoured (an unreadable robots.txt stops the run), at most 1 request per second
  * bounded timeout and body size, HTML only, an identifying User-Agent
  * a page whose sitemap lastmod is not newer than its recorded ingested_at is skipped (only when both dates are valid)

`--write` exists only to say it is not available: a real write to the shared admizz-test namespace is a separate step that needs
explicit approval after this report has been reviewed.

Usage (from backend/):
    .venv311/bin/python -m scripts.ingest_education_sources                    # dry run of admizz-test
    .venv311/bin/python -m scripts.ingest_education_sources --only uk-guide    # one entry
    .venv311/bin/python -m scripts.ingest_education_sources --registry path/to/registry.json
    .venv311/bin/python -m scripts.ingest_education_sources --existing existing_chunks.json --manifest manifest.json

--existing is a JSON snapshot of the tenant's current ingestion jobs (read-only metadata, made separately); this script never
connects to a database. The manifest shows overlap with those jobs, a content class (source_backed / dated / explanatory, never
"verified"), warnings, and the embedding volume a real ingestion would use.
"""
import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Protocol
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.services.education_ingest_plan import (
    ExistingSource, PlanPage, classify_content, find_overlap, plan_ingestion, preflight,
)
from app.services.education_page_dispositions import decide, summary as disposition_summary
from app.services.education_page_extractor import extract_page
from app.services.education_sources import SITE_HOST, Resource, get_sources, is_allowed_url, load_sources_file
from app.utils.chunking import chunk_text

USER_AGENT = ("ZunkireeSearch-SourceIngest/1.0 (+https://github.com/Zunkireelabs/zunkiree-search-v1; "
              "dry run, honours robots.txt, at most 1 request per second)")
ROBOTS_URL = f"https://{SITE_HOST}/robots.txt"
MIN_INTERVAL = 1.0          # seconds between any two requests (robots.txt included)
TIMEOUT = 15.0              # seconds per request
MAX_BYTES = 1_000_000       # a page larger than this is rejected
MAX_REDIRECTS = 3

WRITE_REFUSED = ("--write is not available: a real write to the shared admizz-test knowledge base (Supabase + Pinecone, with paid "
                 "embeddings) needs a separate explicit approval after this dry-run report has been reviewed. Nothing was done.")


class FetchError(Exception):
    pass


class FetchTimeout(FetchError):
    pass


@dataclass
class Fetched:
    status: int
    headers: dict
    body: bytes
    location: str | None = None


class Fetcher(Protocol):
    def fetch(self, url: str) -> Fetched: ...


def _fetchable(url: str) -> bool:
    return is_allowed_url(url) or url == ROBOTS_URL


class HttpxFetcher:
    """One GET, never following a redirect (the caller checks every hop), reading at most MAX_BYTES + 1 bytes."""

    def __init__(self, *, timeout: float = TIMEOUT, max_bytes: int = MAX_BYTES, transport: httpx.BaseTransport | None = None):
        self.timeout, self.max_bytes, self.transport = timeout, max_bytes, transport

    def fetch(self, url: str) -> Fetched:
        if not _fetchable(url):
            raise FetchError(f"refusing to request {url!r}: not an approved url")
        try:
            with httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9"}, timeout=self.timeout,
                              follow_redirects=False, transport=self.transport) as client:
                with client.stream("GET", url) as response:
                    body = bytearray()
                    for part in response.iter_bytes():
                        body.extend(part)
                        if len(body) > self.max_bytes:
                            body = body[: self.max_bytes + 1]      # enough to know it is too big; never download the rest
                            break
                    return Fetched(response.status_code, {k.lower(): v for k, v in response.headers.items()}, bytes(body),
                                   response.headers.get("location"))
        except httpx.TimeoutException as e:
            raise FetchTimeout(str(e)) from e
        except httpx.HTTPError as e:
            raise FetchError(str(e)) from e


class Pacer:
    """Keeps at least `interval` seconds between two requests. Clock and sleep are injectable for tests."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 interval: float = MIN_INTERVAL):
        self._clock, self._sleep, self._interval, self._last = clock, sleep, interval, None

    def wait(self) -> None:
        if self._last is not None:
            remaining = self._interval - (self._clock() - self._last)
            if remaining > 0:
                self._sleep(remaining)
        self._last = self._clock()


def _as_date(value: str | None) -> date | None:
    try:
        return datetime.fromisoformat(value).date() if value else None
    except ValueError:
        return None


def is_fresh(sitemap_lastmod: str | None, ingested_at: str | None) -> bool:
    """True (skip the page) only when both dates are valid and the page has not changed since it was ingested."""
    changed, ingested = _as_date(sitemap_lastmod), _as_date(ingested_at)
    return bool(changed and ingested and ingested >= changed)


@dataclass
class Report:
    fetched: int = 0
    skipped: int = 0
    rejected: dict = field(default_factory=dict)
    rejected_detail: list = field(default_factory=list)
    chunked_pages: int = 0
    total_chunks: int = 0
    eligible: list = field(default_factory=list)
    manifest: list = field(default_factory=list)       # one entry per registry resource, whatever happened to it
    plan: dict = field(default_factory=dict)           # filled by `summarise` from the manifest and the existing-chunks snapshot
    estimate: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    dispositions: list = field(default_factory=list)

    def _entry(self, resource: Resource, **fields) -> dict:
        entry = {"id": resource.id, "registry_url": resource.url, "category": resource.category, "country": resource.country,
                 "kind": resource.kind, "registry_freshness": {"sitemap_lastmod": resource.sitemap_lastmod, "published": resource.published,
                                                               "checked": resource.checked, "ingested_at": resource.ingested_at},
                 "verified": False, **fields}
        self.manifest.append(entry)
        return entry

    def reject(self, reason: str, resource: Resource) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1
        self.rejected_detail.append((resource.id, reason))
        self._entry(resource, eligible=False, reason=reason)

    def skip_fresh(self, resource: Resource) -> None:
        self.skipped += 1
        self._entry(resource, eligible=False, reason="fresh")

    def render(self) -> str:
        lines = ["DRY RUN: nothing was written (no database, no vector store, no embeddings; the registry is untouched).",
                 f"fetched: {self.fetched}",
                 f"skipped (fresh): {self.skipped}",
                 f"rejected: {sum(self.rejected.values())}" + (f"  {self.rejected}" if self.rejected else ""),
                 f"chunked pages: {self.chunked_pages}   chunks in total: {self.total_chunks}",
                 f"eligible for ingestion: {len(self.plan.get('add', []))}   (no page is verified; classes below describe how a page presents itself)"]
        for e in self.eligible:
            flags = [e["content_class"]] + ([f"overlap:{e['overlap']['match']}"] if e.get("overlap") else []) + e["warnings"]
            mark = "+" if e["eligible_for_ingestion"] else "~"
            lines.append(f"  {mark} {e['id']:<26} {e['chunks']:>3} chunks {e['characters']:>6} chars  {e['canonical_url']}  [{', '.join(flags)}]"
                         + ("" if e["eligible_for_ingestion"] else f"  ({e['plan_action']})"))
        lines += [f"  - {rid:<26} rejected: {why}" for rid, why in self.rejected_detail]
        if self.dispositions:
            counts = disposition_summary(self.dispositions)
            lines.append("dispositions: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
        if self.estimate:
            est = self.estimate
            lines += [f"embedding volume if ingested: {est['chunks']} chunks, {est['tokens']} tokens, {est['api_calls']} embedding calls, "
                      f"about ${est['usd']:.4f}", f"  {est['note']}"]
        if self.plan.get("retire_candidates"):
            lines.append("existing chunks that MAY be replaced (title match only, not proof; retire only by explicit job id):")
            lines += [f"  ? job {c['job_id']}  ~ {c['page_id']}  ({c['proof']})" for c in self.plan["retire_candidates"]]
        if self.problems:
            lines += ["PREFLIGHT PROBLEMS:"] + [f"  ! {p}" for p in self.problems]
        return "\n".join(lines)


def _canonical(html: str, page_url: str) -> str:
    link = BeautifulSoup(html, "html.parser").find("link", rel="canonical")
    href = urljoin(page_url, link["href"]) if link and link.get("href") else ""
    return href if is_allowed_url(href) else page_url        # a canonical on another host is ignored


def _load_robots(fetcher: Fetcher, pacer: Pacer) -> RobotFileParser | None:
    """The parsed robots.txt; None when it cannot be read (5xx, timeout, error), which stops the run. A 4xx means 'no rules'."""
    pacer.wait()
    try:
        response = fetcher.fetch(ROBOTS_URL)
    except FetchError:
        return None
    if response.status >= 500:
        return None
    parser = RobotFileParser()
    parser.parse(response.body.decode("utf-8", "replace").splitlines() if response.status == 200 else [])
    return parser


def _fetch_page(resource: Resource, fetcher: Fetcher, pacer: Pacer, robots: RobotFileParser, report: Report,
                existing: list[ExistingSource]) -> None:
    url = resource.url
    for _ in range(MAX_REDIRECTS + 1):
        if not robots.can_fetch(USER_AGENT, url):
            return report.reject("robots", resource)
        pacer.wait()
        try:
            response = fetcher.fetch(url)
        except FetchTimeout:
            return report.reject("timeout", resource)
        except FetchError:
            return report.reject("error", resource)
        if response.status in (301, 302, 303, 307, 308):
            target = urljoin(url, response.location) if response.location else ""
            if not is_allowed_url(target):
                return report.reject("redirect_host" if response.location else f"http_{response.status}", resource)
            url = target
            continue
        break
    else:
        return report.reject("too_many_redirects", resource)

    report.fetched += 1
    if response.status != 200:
        return report.reject(f"http_{response.status}", resource)
    if response.headers.get("content-type", "").split(";")[0].strip().lower() != "text/html":
        return report.reject("content_type", resource)
    if len(response.body) > MAX_BYTES:
        return report.reject("too_large", resource)
    html = response.body.decode("utf-8", "replace")
    page = extract_page(html)
    chunks = chunk_text(page.text)
    if not chunks:
        return report.reject("empty", resource)
    report.chunked_pages += 1
    report.total_chunks += len(chunks)
    canonical, title = _canonical(html, url), page.title or resource.title
    checked_statement = re.search(r"\bchecked (?:in|on) [A-Z][a-z]+ \d{4}", page.text, re.IGNORECASE) is not None
    entry = report._entry(
        resource, eligible=True, url=resource.url, canonical_url=canonical, title=title, characters=len(page.text), chunks=len(chunks),
        tokens=sum(c.get("token_count") or 0 for c in chunks), warnings=page.warnings, dropped_sections=page.dropped,
        references=page.references, has_checked_statement=checked_statement,
        content_sha256=hashlib.sha256(page.text.encode()).hexdigest(),
        content_class=classify_content(has_checked_statement=checked_statement, references=page.references,
                                       published=resource.published, checked=resource.checked),
        overlap=find_overlap(canonical, title, existing))
    report.eligible.append(entry)


def run_dry_run(resources: list[Resource], fetcher: Fetcher, *, pacer: Pacer, existing: list[ExistingSource] | None = None) -> Report:
    existing = list(existing or [])
    report = Report()
    todo: list[Resource] = []
    for resource in resources:
        if not is_allowed_url(resource.url):
            report.reject("url", resource)
        elif is_fresh(resource.sitemap_lastmod, resource.ingested_at):
            report.skip_fresh(resource)
        else:
            todo.append(resource)
    if todo:
        robots = _load_robots(fetcher, pacer)
        if robots is None:
            for resource in todo:
                report.reject("robots_unavailable", resource)
        else:
            for resource in todo:
                _fetch_page(resource, fetcher, pacer, robots, report, existing)
    summarise(report, existing)
    return report


def summarise(report: Report, existing: list[ExistingSource], today: date | None = None) -> None:
    """The plan a real ingestion would follow, from the manifest alone (still nothing is written)."""
    pages = [PlanPage(id=e["id"], canonical_url=e["canonical_url"], title=e["title"], chunks=e["chunks"], tokens=e["tokens"],
                      warnings=e["warnings"], category=e["category"]) for e in report.eligible]
    plan = plan_ingestion(pages, existing)
    report.problems, report.estimate = preflight(plan, existing)
    if not report.eligible:
        report.problems = [p for p in report.problems if p != "nothing to add"]
        report.estimate = {}
    report.plan = {"add": [p.id for p in plan.add], "skip": plan.skip, "retire_candidates": plan.retire_candidates}
    skipped = {s["page_id"]: s["reason"] for s in plan.skip}
    for entry in report.manifest:
        if entry["id"] in report.plan["add"]:
            entry.update(eligible_for_ingestion=True, plan_action="add")
        else:
            reason = skipped.get(entry["id"]) or entry.get("reason") or "not_fetched"
            entry.update(eligible_for_ingestion=False, plan_action=f"skip: {reason}")
    report.dispositions = []
    for entry in report.manifest:     # a manifest entry's disposition: ready / review / excluded / undecided, with reasons and notes
        d = decide(entry, today=today or date.today())
        entry.update(disposition=d.status, disposition_reasons=list(d.reasons), disposition_notes=list(d.notes))
        report.dispositions.append(d)


def main(argv: list[str] | None = None, *, fetcher: Fetcher | None = None, clock: Callable[[], float] = time.monotonic,
         sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", default="admizz-test", help="tenant site_id (default admizz-test)")
    parser.add_argument("--registry", type=Path, help="read this registry file instead of the tenant's")
    parser.add_argument("--only", action="append", default=[], help="only this registry id (repeatable)")
    parser.add_argument("--existing", type=Path, help="JSON snapshot of the tenant's current ingestion jobs (read-only metadata)")
    parser.add_argument("--manifest", type=Path, help="write the JSON manifest of every page to this path")
    parser.add_argument("--limit", type=int, help="at most this many entries")
    parser.add_argument("--write", action="store_true", help="NOT AVAILABLE: needs separate approval")
    args = parser.parse_args(argv)
    if args.write:
        print(WRITE_REFUSED)
        return 2
    registry = load_sources_file(args.registry) if args.registry else get_sources(args.site)
    if registry is None:
        print("could not read the registry", file=sys.stderr)
        return 1
    existing: list[ExistingSource] = []
    if args.existing:
        try:
            existing = [ExistingSource.from_snapshot(row) for row in json.loads(args.existing.read_text())]
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"could not read the existing-chunks snapshot: {e}", file=sys.stderr)
            return 1
    resources = [r for r in registry.resources if not args.only or r.id in args.only][: args.limit]
    report = run_dry_run(resources, fetcher or HttpxFetcher(), pacer=Pacer(clock, sleep), existing=existing)
    print(report.render())
    if args.manifest:
        args.manifest.write_text(json.dumps({"dry_run": True, "note": "No page is verified; content_class describes how a page presents itself.",
                                             "pages": report.manifest, "plan": report.plan, "estimate": report.estimate,
                                             "problems": report.problems, "existing_jobs": len(existing)}, indent=2, ensure_ascii=False) + "\n")
        print(f"manifest written to {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
