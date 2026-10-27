"""
DRY RUN: reads the Admizz UK university pages and reports the University and Course records they would produce.

Finds the universities from the index page https://admizzeducation.com/explore-universities/uk, fetches each university page and parses
it with app/services/education_university_extractor.py. It writes NOTHING to any store and never touches the live catalog
(app/data/education_catalogs): with --out it writes one JSON file you name, for a person to read before anything is used.
Everything it produces is public website text that nobody has verified.

Rules it follows (the same as scripts/ingest_education_sources.py, whose fetcher it reuses):
  * only https pages on the approved host; every redirect hop is checked the same way
  * robots.txt is honoured (an unreadable robots.txt stops the run), at most 1 request per second
  * bounded timeout and body size, HTML only, an identifying User-Agent

Usage (from backend/):
    .venv311/bin/python -m scripts.extract_education_uk_catalog                     # dry run, report only
    .venv311/bin/python -m scripts.extract_education_uk_catalog --only university-of-essex
    .venv311/bin/python -m scripts.extract_education_uk_catalog --out /tmp/uk_catalog_dryrun.json
    .venv311/bin/python -m scripts.extract_education_uk_catalog --fragment app/data/education_catalogs/admizz-test.uk.json

--fragment writes only the university and course records, in the form the catalog provider merges into the tenant's catalog. It is the one
write allowed inside the catalog folder, only for a file named `<site_id>.uk.json`, and only when every page was read.
"""
import argparse
import datetime
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

from app.services.education_catalog import CATALOG_DIR
from app.services.education_sources import SITE_HOST, is_allowed_url
from app.services.education_university_extractor import ParsedUniversity, parse_university_page
from scripts.ingest_education_sources import (
    MAX_BYTES, MAX_REDIRECTS, USER_AGENT, FetchError, Fetcher, FetchTimeout, HttpxFetcher, Pacer, _load_robots,
)

COUNTRY_ID = "uk"
INDEX_URL = f"https://{SITE_HOST}/explore-universities/{COUNTRY_ID}"
# Most links are not <a> tags: the page also carries them inside its embedded script data (escaped quotes), so match the path itself.
_SLUG = re.compile(r"/explore-universities/" + COUNTRY_ID + r"/([a-z0-9]+(?:-[a-z0-9]+)*)(?![a-z0-9-])")
_STATED = re.compile(r"(\d+)\s+universities", re.IGNORECASE)


def university_url(slug: str) -> str:
    return f"{INDEX_URL}/{slug}"


def _get(url: str, fetcher: Fetcher, pacer: Pacer, robots: RobotFileParser) -> tuple[str | None, str | None]:
    """(html, None) or (None, reason). Follows at most MAX_REDIRECTS hops, each checked against the approved host and robots.txt."""
    for _ in range(MAX_REDIRECTS + 1):
        if not is_allowed_url(url):
            return None, "url"
        if not robots.can_fetch(USER_AGENT, url):
            return None, "robots"
        pacer.wait()
        try:
            response = fetcher.fetch(url)
        except FetchTimeout:
            return None, "timeout"
        except FetchError:
            return None, "error"
        if response.status in (301, 302, 303, 307, 308):
            target = urljoin(url, response.location) if response.location else ""
            if not is_allowed_url(target):
                return None, "redirect_host" if response.location else f"http_{response.status}"
            url = target
            continue
        break
    else:
        return None, "too_many_redirects"
    if response.status != 200:
        return None, f"http_{response.status}"
    if response.headers.get("content-type", "").split(";")[0].strip().lower() != "text/html":
        return None, "content_type"
    if len(response.body) > MAX_BYTES:
        return None, "too_large"
    return response.body.decode("utf-8", "replace"), None


def discover(html: str) -> tuple[list[str], int | None]:
    """The university slugs linked from the index page (in page order, no repeats) and the count the page itself states."""
    slugs = list(dict.fromkeys(_SLUG.findall(html)))
    stated = _STATED.search(re.sub(r"<[^>]+>", " ", html))
    return slugs, int(stated.group(1)) if stated else None


class Result:
    def __init__(self):
        self.stated: int | None = None
        self.discovered: list[str] = []
        self.parsed: list[ParsedUniversity] = []
        self.failed: dict[str, str] = {}          # slug -> reason
        self.problems: list[str] = []

    @property
    def courses(self):
        return [c for p in self.parsed for c in p.courses]

    def render(self) -> str:
        courses = self.courses
        by_level = Counter(c.level for c in courses)
        priced = [c.tuition_per_year.amount for c in courses if c.tuition_per_year]
        lines = ["DRY RUN: nothing was written (no database, no vector store, no catalog file). Website text, unverified.",
                 f"universities: page states {self.stated}, links found {len(self.discovered)}, read {len(self.parsed)}, failed {len(self.failed)}",
                 f"courses read: {len(courses)}   by level: {dict(by_level)}",
                 f"courses with a per-year tuition: {len(priced)}   without: {len(courses) - len(priced)}"
                 + (f"   range £{min(priced):,} to £{max(priced):,}" if priced else ""),
                 f"universities with no courses read: {sum(1 for p in self.parsed if not p.courses)}"]
        if self.failed:
            lines.append("FAILED PAGES:")
            lines += [f"  ! {slug}: {why}" for slug, why in self.failed.items()]
        with_warnings = [p for p in self.parsed if p.warnings]
        lines.append(f"universities with warnings: {len(with_warnings)}")
        for p in with_warnings:
            lines.append(f"  ~ {p.university.id} ({len(p.courses)} courses)")
            lines += [f"      - {w}" for w in p.warnings[:5]] + ([f"      - ... and {len(p.warnings) - 5} more"] if len(p.warnings) > 5 else [])
        if self.problems:
            lines += ["PROBLEMS:"] + [f"  ! {p}" for p in self.problems]
        return "\n".join(lines)

    def fragment_text(self) -> str:
        """Records only, one per line so a change shows up as a readable diff. Website text; nobody has verified it."""
        head = {"status": "unverified", "country": COUNTRY_ID, "currency": "GBP", "source": f"{INDEX_URL} and the university pages under it",
                "extracted_on": datetime.date.today().isoformat(),
                "permission": "Admizz confirmed on 2026-10-27 (reported by the project owner) that we may use the numbers on its website.",
                "note": "Read from admizzeducation.com. Permission to use it is not a check that it is right: fees and intakes can change and are not independently verified."}
        dump = lambda records: ",\n".join("    " + json.dumps(r.model_dump(mode="json"), ensure_ascii=False) for r in records)  # noqa: E731
        meta = json.dumps(head, ensure_ascii=False, indent=2)[:-2]
        return (f'{meta},\n  "universities": [\n{dump(p.university for p in self.parsed)}\n  ],\n'
                f'  "courses": [\n{dump(self.courses)}\n  ]\n}}\n')

    def to_json(self) -> dict:
        return {"dry_run": True, "status": "unverified",
                "note": "Public website text read from admizzeducation.com. Nobody has verified it; do not present it as confirmed.",
                "country": COUNTRY_ID, "currency": "GBP",
                "stated_university_count": self.stated, "failed_pages": self.failed, "problems": self.problems,
                "universities": [p.university.model_dump(mode="json") for p in self.parsed],
                "courses": [c.model_dump(mode="json") for c in self.courses],
                "warnings": {p.university.id: p.warnings for p in self.parsed if p.warnings},
                "last_verified": {p.university.id: p.last_verified for p in self.parsed}}


def run(fetcher: Fetcher, *, pacer: Pacer, only: list[str] | None = None, limit: int | None = None) -> Result:
    result = Result()
    robots = _load_robots(fetcher, pacer)
    if robots is None:
        result.problems.append("robots.txt could not be read; nothing was fetched")
        return result
    index, why = _get(INDEX_URL, fetcher, pacer, robots)
    if index is None:
        result.problems.append(f"the UK index page could not be read ({why})")
        return result
    result.discovered, result.stated = discover(index)
    if result.stated is not None and result.stated != len(result.discovered):
        result.problems.append(f"the page states {result.stated} universities but {len(result.discovered)} links were found")
    if not result.discovered:
        result.problems.append("no university links found on the index page")
    slugs = [s for s in result.discovered if not only or s in only][:limit]
    for slug in slugs:
        html, why = _get(university_url(slug), fetcher, pacer, robots)
        if html is None:
            result.failed[slug] = why or "error"
            continue
        parsed = parse_university_page(html, slug=slug, country_id=COUNTRY_ID, url=university_url(slug))
        if parsed is None:
            result.failed[slug] = "not_a_university_page"
        else:
            result.parsed.append(parsed)
    return result


def main(argv: list[str] | None = None, *, fetcher: Fetcher | None = None, clock: Callable[[], float] = time.monotonic,
         sleep: Callable[[float], None] = time.sleep) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", action="append", default=[], help="only this university slug (repeatable)")
    parser.add_argument("--limit", type=int, help="at most this many universities")
    parser.add_argument("--out", type=Path, help="write the records and warnings as JSON to this path (never inside the live catalog folder)")
    parser.add_argument("--fragment", type=Path, help="write the records the catalog provider merges, as <site_id>.uk.json")
    args = parser.parse_args(argv)
    if args.fragment and not re.fullmatch(r"[A-Za-z0-9_-]+\.uk\.json", args.fragment.name):
        print("--fragment must be named <site_id>.uk.json, for example admizz-test.uk.json.", file=sys.stderr)
        return 1
    if args.out and CATALOG_DIR.resolve() in args.out.resolve().parents:
        print(f"refusing to write inside {CATALOG_DIR}: this dry run must not change the live catalog.", file=sys.stderr)
        return 1
    result = run(fetcher or HttpxFetcher(), pacer=Pacer(clock, sleep), only=args.only, limit=args.limit)
    print(result.render())
    if args.out:
        args.out.write_text(json.dumps(result.to_json(), indent=2, ensure_ascii=False) + "\n")
        print(f"records written to {args.out}")
    if args.fragment:
        if result.failed or result.problems or not result.parsed:
            print("not writing the records file: some pages failed or the run had problems.", file=sys.stderr)
            return 1
        args.fragment.write_text(result.fragment_text())
        print(f"records file written to {args.fragment}")
    return 1 if result.problems and not result.parsed else 0


if __name__ == "__main__":
    sys.exit(main())
