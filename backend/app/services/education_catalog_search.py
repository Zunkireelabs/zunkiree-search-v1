"""
Looking up universities and courses in a tenant's catalog. Pure, deterministic Python: no LLM, no network.

A question such as "MSc data science in the UK" is turned into fixed filters (country, level, subject words, one university)
and the catalog's own records are filtered with them. Nothing here invents a course, a fee or a university: a field the
catalog does not state is simply not shown.

Fees are shown the way the source states them: a plain yearly figure, a whole-course total, or the source's own wording
("from £9,400 per year · £9,400–£17,700 depending on course") for a price that varies by course. There is no currency
conversion, so a course fee is never compared with the student's budget (the budget is in the catalog's country currency).
"""
import re
from dataclasses import dataclass

from app.services.education_catalog import Catalog
from app.services.education_catalog_models import Course
from app.services.money import format_money_range

MAX_RESULTS = 6
LEVEL_LABELS = {"foundation": "Foundation", "bachelor": "Bachelor's", "master": "Master's", "phd": "PhD"}

_LEVEL_WORDS = {
    "master": ("master", "masters", "master's", "msc", "mba", "llm", "postgraduate", "postgrad", "graduate", "grad", "pg", "ma"),
    "bachelor": ("bachelor", "bachelors", "bachelor's", "bsc", "beng", "undergraduate", "undergrad", "ug", "ba"),
    "foundation": ("foundation",),
    "phd": ("phd", "doctorate", "doctoral"),
}
_WORD_LEVEL = {w: level for level, words in _LEVEL_WORDS.items() for w in words}
# Degree abbreviations tell the level AND are part of a course's name ("MSc Data Science", "MBA"), so they stay search terms.
_DEGREE_ABBREVIATIONS = {"msc", "mba", "llm", "ma", "bsc", "ba", "beng"}

# Words that say "I want courses" or are plain grammar, never a subject. Everything else in the question is a subject word.
_STOP = set("""
a an the and or of in on at for to from with without by about as is are was be do does can could would should will my me i we you your our
what which who whom where when how why please recommend recommended recommendation suggest suggestions advice help have has had having did doing show tell give find list any some all more most best good top cheap cheapest lowest low high
want wanted wants need looking look like am im try trying go going goes plan planning planned wish interested interest would love hope hoping hope pursue pursuing join joining do doing study studying studied apply get take taking offer offers offered offering available there here
course courses program programs programme programmes degree degrees subject subjects university universities college colleges
fee fees tuition cost costs price prices much many option options choice choices related related another other
abroad country countries uk england britain united kingdom
""".split())
_SYNONYMS = {"cs": ("computer", "science"), "ai": ("artificial", "intelligence"), "ml": ("machine", "learning")}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9' ]+", " ", (text or "").lower().replace("&", " and ")).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", _norm(text))


@dataclass(frozen=True)
class CourseQuery:
    country: str | None = None
    level: str | None = None
    terms: tuple[str, ...] = ()         # subject words; a course must contain every one
    university: str | None = None       # a university id


def level_in_text(text: str) -> str | None:
    for word in _words(text):
        if word in _WORD_LEVEL:
            return _WORD_LEVEL[word]
    return None


def subject_terms(text: str, catalog: Catalog, university_ids: list[str] | None = None) -> tuple[str, ...]:
    """The subject words of a question: what is left after level words, country names, the words of a named university,
    grammar and course/university words."""
    country_words = {w for c in catalog.countries for name in [c.label, c.id, *c.aliases] for w in _words(name)}
    for uid in university_ids or []:
        university = catalog.get_university(uid)
        if university:
            country_words |= {w for v in _name_variants(university.name) for w in _words(v)}
    terms: list[str] = []
    for word in _words(text):
        word = word.strip("'")
        if word.endswith("'s"):
            word = word[:-2]
        level_only = word in _WORD_LEVEL and word not in _DEGREE_ABBREVIATIONS
        if not word or word in _STOP or level_only or word in country_words or word.isdigit():
            continue
        for part in _SYNONYMS.get(word, (word,)):
            if part not in terms:
                terms.append(part)
    return tuple(terms)


# ---- universities ----

def _strip_generic(name: str) -> str:
    return re.sub(r"^(the )?university of |\buniversity$", "", _norm(name)).strip()


def _name_variants(name: str) -> list[str]:
    """The ways a student may write a university's name: in full, without a trailing "(...)", and without "University of"."""
    plain = _norm(re.sub(r"\(.*?\)", " ", name))
    out: list[str] = []
    for base in (_norm(name), plain):
        for candidate in (base, _strip_generic(base)):
            candidate = " ".join(candidate.split())
            if candidate and candidate not in out:
                out.append(candidate)
    return out


def without_university_names(catalog: Catalog, text: str, university_ids: list[str]) -> str:
    """The text with the named universities' names cut out, so the "university" in "Arden University" is not read as a request for
    universities in general."""
    out = f" {_norm(text)} "
    for uid in university_ids:
        university = catalog.get_university(uid)
        for variant in sorted(_name_variants(university.name), key=len, reverse=True) if university else []:
            out = out.replace(f" {variant} ", " ")
    return out.strip()


def universities_in_text(catalog: Catalog, text: str) -> list[str]:
    """Ids of the universities the text names (the full name, or the name without "University of"/"University"). When one
    matched name contains another ("Aston University OnCampus" and "Aston University") only the longer one counts."""
    haystack = f" {_norm(text)} "
    hits: dict[str, str] = {}
    for u in catalog.universities:
        for candidate in _name_variants(u.name):
            if len(candidate) >= 4 and f" {candidate} " in haystack:
                hits[u.id] = max(hits.get(u.id, ""), candidate, key=len)
    for uid, name in list(hits.items()):
        if any(other != uid and name != n and name in n for other, n in hits.items()):
            del hits[uid]
    return list(hits)


# ---- courses ----

def _country_of(catalog: Catalog, course: Course) -> str | None:
    university = catalog.get_university(course.university_id)
    return university.country_id if university else None


def _has_word(words: list[str], term: str) -> bool:
    """A whole word of the course name, or (for a term of 4+ letters) the start of one: "account" finds "accounting"."""
    return any(w == term or (len(term) >= 4 and w.startswith(term)) for w in words)


def search_courses(catalog: Catalog, query: CourseQuery) -> list[Course]:
    """Every matching course, cheapest known yearly fee first (a course without a yearly figure comes after), then by name."""
    found: list[Course] = []
    for course in catalog.courses:
        if query.university and course.university_id != query.university:
            continue
        if query.country and _country_of(catalog, course) != query.country:
            continue
        if query.level and course.level != query.level:
            continue
        words = _words(f"{course.name} {course.field_of_study or ''}")
        if not all(_has_word(words, term) for term in query.terms):
            continue
        found.append(course)
    found.sort(key=lambda c: (c.tuition_per_year is None, c.tuition_per_year.amount if c.tuition_per_year else 0, c.name.lower(), c.id))
    return found


def pick_results(courses: list[Course], *, one_per_university: bool, limit: int = MAX_RESULTS) -> list[Course]:
    """The courses to show. For a broad search (no single university) at most one course per university, so the list is a
    spread of universities and not six near-identical rows from one."""
    if not one_per_university:
        return courses[:limit]
    seen: set[str] = set()
    out: list[Course] = []
    for course in courses:
        if course.university_id in seen:
            continue
        seen.add(course.university_id)
        out.append(course)
        if len(out) == limit:
            break
    return out


# ---- how a course is described ----

def terms_label(terms: tuple[str, ...]) -> str:
    """Subject words for display: "msc data science" -> "MSc Data Science" (degree abbreviations keep their usual capitals)."""
    caps = {"msc": "MSc", "mba": "MBA", "llm": "LLM", "bsc": "BSc", "beng": "BEng", "ma": "MA", "ba": "BA"}
    return " ".join(caps.get(t, t.title()) for t in terms)


def fee_text(course: Course) -> str | None:
    """The fee as the source states it. None when the source gave nothing."""
    if course.tuition_per_year:
        return f"{course.tuition_per_year.format()} / year"
    if course.tuition_total:
        return f"{course.tuition_total.format()} total"
    return course.tuition_note


def duration_text(months: int | None) -> str | None:
    if not months:
        return None
    if months % 12 == 0:
        years = months // 12
        return f"{years} year" + ("s" if years != 1 else "")
    return f"{months} months"


def ielts_text(course: Course) -> str | None:
    return f"IELTS {course.ielts_min:g}" if course.ielts_min is not None else None


def tuition_range(courses: list[Course]) -> str | None:
    """A yearly range over the courses that state a plain yearly figure in one currency, or None."""
    figures = [c.tuition_per_year for c in courses if c.tuition_per_year]
    currencies = {m.currency for m in figures}
    if not figures or len(currencies) != 1:
        return None
    currency = currencies.pop()
    return format_money_range(min(m.amount for m in figures), max(m.amount for m in figures), currency) + " / year"


def level_counts(courses: list[Course]) -> str:
    order = ("foundation", "bachelor", "master", "phd")
    counts = [(level, sum(1 for c in courses if c.level == level)) for level in order]
    return ", ".join(f"{n} {LEVEL_LABELS[level].lower()}" for level, n in counts if n)
