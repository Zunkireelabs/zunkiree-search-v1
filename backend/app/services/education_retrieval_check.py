"""Is the new content actually FOUND? The check run after an approved ingestion.

"Stored and verified in both stores" does not mean the chatbot will retrieve a page when a student asks about it. For each page there is a short list of
probe questions (questions only: no answers, no facts), and a page passes when, for every question, that page's own canonical url is among the top
results of the real retrieval. The retrieval itself is injected (`retrieve(question) -> list of chunk dicts`), so this module makes no call of its own.

What it cannot do: judge whether the retrieved text is useful or correct. It records which urls were found instead, so a person can read the answers
before anything old is retired. A failing or missing check never passes by accident.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

TOP_N = 3
MAX_PROBES_PER_PAGE = 5
MAX_PROBE_LENGTH = 200
_PLAIN_ID = re.compile(r"[a-z0-9_-]+")


@dataclass
class ProbeResult:
    question: str
    found: bool = False
    rank: int | None = None                         # 1 = the best result
    top_sources: list = field(default_factory=list)  # the urls retrieved, in order (what was found instead, when it fails)
    error: str | None = None


@dataclass
class PageCheck:
    page_id: str
    results: list = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(r.found for r in self.results)


def load_probes(path: Path) -> dict[str, list[str]]:
    """page id -> its probe questions; ValueError if the file is not a valid probe file."""
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise ValueError(f"probe file unreadable: {e}") from e
    probes = doc.get("probes") if isinstance(doc, dict) else None
    if not isinstance(probes, dict):
        raise ValueError("a probe file is {probes: {page_id: [questions]}}")
    for page_id, questions in probes.items():
        if not _PLAIN_ID.fullmatch(page_id or ""):
            raise ValueError(f"{page_id!r} is not a plain page id")
        if not isinstance(questions, list) or not 1 <= len(questions) <= MAX_PROBES_PER_PAGE:
            raise ValueError(f"{page_id}: give 1 to {MAX_PROBES_PER_PAGE} questions")
        for question in questions:
            if not isinstance(question, str) or not question.strip() or len(question) > MAX_PROBE_LENGTH:
                raise ValueError(f"{page_id}: every question must be a non-empty string of at most {MAX_PROBE_LENGTH} characters")
    return {page_id: [q.strip() for q in questions] for page_id, questions in probes.items()}


def pilot_probe_problems(pages, probes: dict[str, list[str]]) -> list[str]:
    """Reported BEFORE anything is written: a page that cannot be checked afterwards should not be ingested blind."""
    return [f"{p.id}: no probe questions, so retrieval cannot be checked" for p in pages if not probes.get(p.id)]


async def check_page(retrieve: Callable[[str], Awaitable[list]], page, questions: list[str], top_n: int = TOP_N) -> PageCheck:
    check = PageCheck(page.id)
    for question in questions:
        result = ProbeResult(question)
        try:
            chunks = (await retrieve(question) or [])[:top_n]
        except Exception as error:      # a search that fails is a page that did not pass
            result.error = f"{type(error).__name__}: {str(error)[:100]}"
            check.results.append(result)
            continue
        urls = [c.get("source_url") if isinstance(c, dict) else None for c in chunks]
        result.top_sources = [u for u in urls if isinstance(u, str) and u]
        if page.canonical_url in urls:
            result.found, result.rank = True, urls.index(page.canonical_url) + 1
        check.results.append(result)
    return check


def make_retrieval_check(retrieve: Callable[[str], Awaitable[list]], probes: dict[str, list[str]], top_n: int = TOP_N):
    """The hook `retire_confirmed_jobs` wants: `await hook(page) -> bool`. The details of each page's check are kept in `hook.checks`."""
    async def hook(page) -> bool:
        check = await check_page(retrieve, page, probes.get(page.id) or [], top_n)
        hook.checks[:] = [c for c in hook.checks if c.page_id != page.id] + [check]
        return check.passed
    hook.checks = []
    return hook
