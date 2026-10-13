"""Links to the tenant's public website pages, with their provenance dates.

This is a registry of LINKS, not of facts: every entry is public website content that nobody has verified (`verified` is always
false here), and nothing in it is a university, course, fee, requirement or visa record. Catalog data (education_catalog.py)
stays the only source of facts on cards. The chatbot uses the registry to point a student at the right page ("More on Admizz:
[...]"), chosen by what they asked about and the country in context, never because a country was merely selected.

Only https links on the approved host are ever shown, whatever the registry file or a retrieved knowledge-base chunk contains.
"""
import calendar
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger("zunkiree.education_sources")

SOURCES_DIR = Path(__file__).resolve().parent.parent / "data" / "education_sources"
SITE_HOST = "admizzeducation.com"

Category = Literal["guide", "visa", "cost", "scholarship", "test_prep", "application", "contact"]
Kind = Literal["answer", "guide", "article", "service"]
_KIND_RANK = {"answer": 0, "guide": 1, "article": 2, "service": 3}
# Generic pages that help whatever the country: a fallback only when the country has no page of that category.
_SHARED_CATEGORIES = ("test_prep", "scholarship", "application", "visa", "contact")

_PATH_OK = re.compile(r"/[A-Za-z0-9/_-]*")
_PLAIN_ID = re.compile(r"[a-z0-9_-]+")


def is_allowed_url(url: object) -> bool:
    """https, the approved host exactly, no credentials/port/query/fragment, and a path that cannot break out of a Markdown link."""
    if not isinstance(url, str) or not url or url != url.strip():
        return False
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (parts.scheme == "https" and parts.hostname == SITE_HOST and parts.username is None and parts.password is None
            and port is None and not parts.query and not parts.fragment and bool(_PATH_OK.fullmatch(parts.path)))


def _iso_date(value: str | None, name: str, *, month_ok: bool = False) -> str | None:
    if value is None:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            date.fromisoformat(value)
            return value
        if month_ok and re.fullmatch(r"\d{4}-\d{2}", value):
            datetime.strptime(value, "%Y-%m")
            return value
    except ValueError:
        pass
    raise ValueError(f"{name} must be an ISO date (YYYY-MM-DD{' or YYYY-MM' if month_ok else ''}), never free text")


class Resource(BaseModel):
    id: str
    country: str | None = None            # a catalog country id; None = useful for any country
    url: str
    title: str = Field(min_length=1, max_length=120)
    category: Category
    kind: Kind
    sitemap_lastmod: str | None = None    # from the website's sitemap: when the page changed, NOT proof it is accurate
    published: str | None = None          # the page's own stated publication date
    checked: str | None = None            # when the page says it was checked (YYYY-MM or YYYY-MM-DD); never inferred
    verified: bool = False                # always false: promoting website text to verified is a separate human decision
    ingested_at: str | None = None        # set only by an approved ingestion

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not _PLAIN_ID.fullmatch(v):
            raise ValueError("id must be a plain lowercase id")
        return v

    @field_validator("country")
    @classmethod
    def _country(cls, v: str | None) -> str | None:
        if v is not None and not _PLAIN_ID.fullmatch(v):
            raise ValueError("country must be a plain lowercase catalog id")
        return v

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        if not is_allowed_url(v):
            raise ValueError(f"url is not an https link on {SITE_HOST}")
        return v

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        if re.search(r"[\r\n]", v):
            raise ValueError("title must be one line")
        return v.strip()

    @field_validator("sitemap_lastmod", "published")
    @classmethod
    def _plain_date(cls, v: str | None, info) -> str | None:
        return _iso_date(v, info.field_name)

    @field_validator("checked")
    @classmethod
    def _checked(cls, v: str | None) -> str | None:
        return _iso_date(v, "checked", month_ok=True)

    @field_validator("ingested_at")
    @classmethod
    def _ingested(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            datetime.fromisoformat(v)
        except ValueError as e:
            raise ValueError("ingested_at must be an ISO date or datetime") from e
        return v

    @field_validator("verified")
    @classmethod
    def _never_verified(cls, v: bool) -> bool:
        if v:
            raise ValueError("website pages stay verified=false in this registry")
        return v


class SourceRegistry(BaseModel):
    site_id: str
    resources: list[Resource] = []


def load_sources_file(path: Path) -> SourceRegistry | None:
    """The registry in `path`, or None if the file is unusable. One bad entry is dropped; the rest still load."""
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        logger.error("education sources %s unreadable: %s", path.name, e)
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("site_id"), str) or not isinstance(doc.get("resources"), list):
        logger.error("education sources %s is invalid: expected {site_id, resources: [...]}", path.name)
        return None
    resources: list[Resource] = []
    seen: set[str] = set()
    for i, entry in enumerate(doc["resources"]):
        try:
            resource = Resource.model_validate(entry)
        except ValidationError as e:
            logger.warning("education sources %s: entry %d dropped: %s", path.name, i, e.errors()[0].get("msg"))
            continue
        if resource.id in seen:
            logger.warning("education sources %s: duplicate id %s dropped", path.name, resource.id)
            continue
        seen.add(resource.id)
        resources.append(resource)
    return SourceRegistry(site_id=doc["site_id"], resources=resources)


class SourceProvider(Protocol):
    def load(self, site_id: str) -> SourceRegistry | None: ...


class JsonFileSourceProvider:
    """One <site_id>.json per tenant in a directory (the same seam as the catalog)."""

    def __init__(self, directory: Path = SOURCES_DIR):
        self.directory = directory

    def load(self, site_id: str) -> SourceRegistry | None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", site_id or ""):
            return None  # never build a file path from anything but a plain id
        path = self.directory / f"{site_id}.json"
        return load_sources_file(path) if path.is_file() else None


_registry: dict[str, SourceRegistry] = {}
_providers: list[SourceProvider] = [JsonFileSourceProvider()]


def register_sources(registry: SourceRegistry) -> None:
    _registry[registry.site_id] = registry


def set_source_providers(providers: list[SourceProvider]) -> None:
    global _providers
    _providers = list(providers)


def reset_sources() -> None:
    """Forget cached registries (tests)."""
    _registry.clear()


def get_sources(site_id: str) -> SourceRegistry:
    """The tenant's registry, or an empty one (the chatbot then simply adds no link)."""
    if site_id in _registry:
        return _registry[site_id]
    for provider in _providers:
        try:
            registry = provider.load(site_id)
        except Exception:  # a failing source must never take the chat down
            logger.exception("education source provider %s failed for %s", type(provider).__name__, site_id)
            continue
        if registry:
            _registry[site_id] = registry
            return registry
    return SourceRegistry(site_id=site_id)


def resources_for(site_id: str, country: str | None, category: str | None = None, kind: str | None = None,
                  include_shared: bool = False) -> list[Resource]:
    """Resources for a country (and optionally a category / kind), answers first. Shared pages only when asked for."""
    country = (country or "").strip().lower() or None
    found = [r for r in get_sources(site_id).resources
             if (category is None or r.category == category) and (kind is None or r.kind == kind)
             and ((country is not None and r.country == country) or (include_shared and r.country is None))]
    return sorted(found, key=lambda r: _KIND_RANK[r.kind])   # sorted() is stable: registry order within a kind


# --- what the student asked about ------------------------------------------------------------------------------------

_I = re.IGNORECASE
_TESTS = r"(?:ielts|pte|toefl|gre|sat|duolingo)"
_PREP = r"(?:prep|prepare|preparing|preparation|coaching|class|classes|course|courses|training|tips|practice|mock|crack|test prep)"
_RULES: list[tuple[str, re.Pattern]] = [
    ("test_prep", re.compile(rf"\b{_TESTS}\b.*\b{_PREP}\b|\b{_PREP}\b.*\b{_TESTS}\b|\btest prep", _I)),
    ("scholarship", re.compile(r"\bscholarships?\b|\bfinancial aid\b|\bfee waivers?\b|\bfunding\b", _I)),
    ("visa", re.compile(r"\bvisas?\b|\bf-?1\b|\bstudy permit\b|\bblocked account\b|\bbank balance\b|\btb test\b"
                        r"|\bhealth surcharge\b|\bbiometrics?\b|\bpal\b|\bcas letter\b", _I)),
    ("cost", re.compile(r"\bcosts?\b|\bfees?\b|\btuition\b|\bexpenses?\b|\bafford\b|\bliving\b|\bprices?\b", _I)),
    ("application", re.compile(r"\bappl(?:y|ying|ication|ications)\b|\bdocuments?\b|\bsop\b|\blor\b|\bintakes?\b"
                               r"|\bdeadlines?\b|\badmissions?\b|\brequirements?\b", _I)),
]
_CATEGORY_FOR_INTENT = {"country_facts": "guide", "cost_calculator": "cost"}


def category_for_question(text: str) -> str | None:
    for category, rx in _RULES:
        if text and rx.search(text):
            return category
    return None


def category_for_intent(intent: str | None) -> str | None:
    """Only the cards that are ABOUT a country's information or cost get a link; no other card does."""
    return _CATEGORY_FOR_INTENT.get(intent or "")


# --- the line shown to the student -----------------------------------------------------------------------------------

def _checked_text(checked: str) -> str:
    year, month, *day = checked.split("-")
    name = f"{calendar.month_name[int(month)]} {year}"
    return f"{int(day[0])} {name}" if day else name


_URLISH = re.compile(r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|io|co|edu|np|info|xyz|app|dev)\b", re.IGNORECASE)


def _clean_title(title: str) -> str:
    """A link label that is plain words: no brackets (cannot close the link), and no web address that could pose as another site."""
    text = _URLISH.sub(" ", re.sub(r"[\[\]()\r\n]", " ", title or ""))
    return re.sub(r"\s+", " ", text).strip()[:100]


def link_line(resource: Resource) -> str:
    """`More on Admizz: [Title](url)`, with the checked date only when the source states one. Empty if the url is not approved."""
    if not is_allowed_url(resource.url):
        return ""
    title = _clean_title(resource.title) or "Admizz Education"
    line = f"More on Admizz: [{title}]({resource.url})"
    return f"{line} (checked {_checked_text(resource.checked)})" if resource.checked else line


_STOPWORDS = frozenset("a an and are can do does for how i in is it me my of on or the to what when where which will you".split())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 and w not in _STOPWORDS}


def _score(resource: Resource, question: str) -> int:
    return len(_words(question) & _words(f"{resource.title} {resource.id}"))


def suggest_link(site_id: str, *, country: str | None, category: str | None, question: str = "",
                 kb_chunks: list[dict] | tuple = (), shown_urls: set[str] | frozenset = frozenset(),
                 fallback_guide: bool = False) -> tuple[str, str] | None:
    """(line, url) for ONE relevant page, or None. Never an unapproved url, never one already shown to this student.

    A retrieved knowledge-base chunk's own page wins (it is what the answer rests on); otherwise the registry page for the
    country and category, answers first and best word match first; a generic page only when the country has none."""
    for chunk in kb_chunks:
        url = chunk.get("source_url")
        if not is_allowed_url(url) or url in shown_urls:
            continue
        known = next((r for r in get_sources(site_id).resources if r.url == url), None)
        resource = known or Resource(id="kb", url=url, title=_clean_title(chunk.get("source_title") or "") or "Admizz Education",
                                     category="guide", kind="guide")
        return link_line(resource), url

    for wanted in (category, "guide" if fallback_guide and country else None):
        if not wanted:
            continue
        pool = resources_for(site_id, country, wanted) if country else []
        if not pool and wanted in _SHARED_CATEGORIES:
            pool = resources_for(site_id, None, wanted, include_shared=True)
        pool = [r for r in pool if r.url not in shown_urls]
        if pool:
            best = max(pool, key=lambda r: (_score(r, question), -pool.index(r)))   # ties keep the answers-first order
            if line := link_line(best):
                return line, best.url
    return None


def _context_country(catalog, profile: dict, intent_args: dict, question: str) -> str | None:
    """The country the reply is about: named by the card, else in the question, else the one the student is looking at."""
    named = str(intent_args.get("country") or "")
    if named and catalog.get(named):
        return named
    for text in (named, question):
        if text and (found := catalog.find_in_text(text)):
            return found[0]
    if profile.get("focus_country") and catalog.get(profile["focus_country"]):
        return profile["focus_country"]
    selected = profile.get("countries") or []
    return selected[0] if len(selected) == 1 and catalog.get(selected[0]) else None


def link_for_turn(site_id: str, catalog, profile: dict, *, question: str, intent: str | None, intent_args: dict | None,
                  kb_chunks: list[dict], kb_miss: bool) -> tuple[str, str] | None:
    """The one link (if any) to add to this reply. `intent` is the card shown (by a rule or by the AI's tool), if any.

    A card gets a link only when it is about a country's information or cost; a question gets one only when it is about a
    topic we have pages for. A selected country on its own never adds a link."""
    shown = set(profile.get("links_shown") or [])
    country = _context_country(catalog, profile, intent_args or {}, question)
    asked = category_for_question(question)
    if intent:
        category = category_for_intent(intent)
        if not category:
            return None
        if asked in ("visa", "scholarship", "test_prep"):   # "what is the uk student visa fee": the visa page beats the cost page
            category = asked
        return suggest_link(site_id, country=country, category=category, question=question, shown_urls=shown)
    if not asked and not kb_miss:
        return None
    return suggest_link(site_id, country=country, category=asked, question=question, shown_urls=shown,
                        kb_chunks=kb_chunks if asked else (), fallback_guide=kb_miss)
