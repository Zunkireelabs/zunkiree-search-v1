"""
Grounding check for sentences the LLM writes freely (English only).

Cards, buttons and lead-ins are built by code, but when the LLM answers in plain text it can still state things nobody gave
it: a live run turned Admizz's own "high visa approval rate" into "Canada has a high visa approval rate", and offered to
"explore universities or programs" that don't exist in our data. A prompt rule can't stop that reliably, so this checks the
finished answer in code, with no extra LLM call:

  * A sentence that makes a RISKY claim (visa outcomes, scholarships, rankings, deadlines, employment / work rights, cost
    comparisons, admission chances, or any number) is kept only if something we actually hold backs it: the knowledge-base text
    retrieved for this turn, the tenant catalog, the student's own profile, a card shown this turn, or the student's message.
    "Backs it" means: within two adjacent lines of ONE source, the same kind of claim, the same countries (and "we"/the
    brand if the sentence is about us), and the same numbers.
  * A QUESTION offering universities / programs / courses is dropped while the catalog has none to show.
  * Anything else (greetings, "what would you like to do next?") passes untouched.

Unsupported sentences are dropped, never rewritten. If nothing is left the caller uses the honest "I don't have that detail".
It is deliberately conservative: when in doubt it drops, because a missing sentence is cheaper than a wrong claim.
"""
import re
from dataclasses import dataclass, field

from app.services.education_catalog import Catalog
from app.services.education_profile import profile_rows

# Kinds of claim that need backing. The same patterns find the claim in the answer and in the sources.
CLAIMS: dict[str, re.Pattern] = {k: re.compile(v, re.I) for k, v in {
    "visa_outcome": r"visa (approval|success|guarantee)|approval rate|success rate|guarantee\w*",
    "scholarship": r"scholarship",
    "ranking": r"\b(ranked|rankings?|top[- ]?\d+|league table)\b",
    "deadline": r"\bdeadlines?\b",
    "outcomes": r"\b(employment|employability|salary|salaries|placement|job (offers?|prospects|market)|work rights?|"
                r"work permit|post-study|permanent residen\w+)\b",
    "cost_comparison": r"\b(cheaper|cheapest|more expensive|less expensive|lower (tuition|fees?|costs?)|"
                       r"higher (tuition|fees?|costs?)|affordable)\b",
    "admission": r"\b(admission|acceptance) (chances?|rate)\b|\bchances? of (admission|acceptance|getting in)\b",
}.items()}

# Words that make a claim absolute. If the answer says one, the backing text must say it too ("guarantees visa approval" is not
# backed by "a high approval rate"). (Idioms like "always happy to help" are deliberately not in this list.)
_STRONG = re.compile(r"\b(guarantee\w*|100\s?%|every student|all students)\b", re.I)
# An honest disclaimer ("we cannot guarantee visa approval") makes no claim to back.
_DISCLAIMER = re.compile(r"\b(cannot|can't|can not|do not|don't|does not|doesn't|unable to|no one can|not able to)\b", re.I)

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_UNDELIVERABLE_OFFER = re.compile(r"\b(universit\w+|colleges?|programs?|courses?)\b", re.I)
_BRAND_WORDS = r"we|our|us"


def _numbers(text: str) -> set[str]:
    out = set()
    for raw in _NUMBER.findall(text):
        out.add(raw.replace(",", "").rstrip("."))
    return out


def _segments(text: str) -> list[str]:
    """Lines / sentences of a source. Scraped pages are messy, so split on sentence ends and newlines."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


@dataclass
class Checked:
    text: str
    dropped: int = 0
    kept: int = 0
    reasons: list[str] = field(default_factory=list)   # claim kinds only; never the text

    @property
    def empty(self) -> bool:
        return not self.text.strip()


def catalog_sources(catalog: Catalog) -> list[list[str]]:
    """The catalog as one short statement per country, in words the claim patterns recognise."""
    docs = []
    for c in catalog.countries:
        parts = [f"{c.label} {' '.join(c.aliases)}:"]
        if c.tuition_min is not None and c.tuition_max is not None:
            parts.append(f"tuition {c.tuition_min} to {c.tuition_max} per year;")
        if c.living_min is not None and c.living_max is not None:
            parts.append(f"living costs {c.living_min} to {c.living_max} per year;")
        if c.yearly_min is not None and c.yearly_max is not None:
            parts.append(f"total yearly cost {c.yearly_min} to {c.yearly_max};")
        if c.intakes:
            parts.append(f"intakes {', '.join(c.intakes)};")
        if c.ielts_min is not None:
            parts.append(f"IELTS minimum {c.ielts_min:g};")
        if c.academic_min_percent is not None:
            parts.append(f"academic minimum {c.academic_min_percent:g} percent;")
        if c.work_rights:
            parts.append(f"work rights {c.work_rights};")
        if c.post_study_visa:
            parts.append(f"post-study work visa {c.post_study_visa};")
        if c.funds_required:
            parts.append(f"proof of funds {c.funds_required};")
        docs.append([" ".join(parts)])
    return docs


# Sources about the STUDENT or the card on screen. A bare number (no claim, no country in the sentence) can only rest on these:
# otherwise "your budget is $30,000" would be "backed" by an unrelated 30000 somewhere in a country's cost range.
PERSONAL = "personal"


@dataclass(frozen=True)
class Source:
    origin: str            # "kb" | "catalog" | PERSONAL
    lines: list[str]


def build_support(chunks: list[dict], catalog: Catalog, profile: dict, shown_texts: list[str], question: str) -> list[Source]:
    """Everything an answer may legitimately rest on."""
    docs = [Source("kb", _segments(c.get("content", ""))) for c in chunks]
    docs += [Source("catalog", lines) for lines in catalog_sources(catalog)]
    rows = profile_rows(profile, catalog.labels(), catalog.currency)
    if rows:
        docs.append(Source(PERSONAL, [f"{r['label']}: {r['value']}" for r in rows]))
    docs += [Source(PERSONAL, [t]) for t in shown_texts if t]
    docs.append(Source(PERSONAL, [question]))
    return docs


def _entities(text: str, catalog: Catalog, brand_word: str) -> set[str]:
    found = set(catalog.find_in_text(text))
    brand = rf"\b({re.escape(brand_word)}|{_BRAND_WORDS})\b" if brand_word else rf"\b({_BRAND_WORDS})\b"
    if re.search(brand, text, re.I):
        found.add("<brand>")
    return found


def _split_sentences(answer: str, catalog: Catalog) -> list[str]:
    protected = answer.strip()
    abbreviations = {w for c in catalog.countries for w in (c.label, *c.aliases) if "." in w}
    for abbr in sorted(abbreviations, key=len, reverse=True):
        protected = protected.replace(abbr, abbr.replace(".", "\x00"))
    return [s.replace("\x00", ".").strip() for s in re.split(r"(?<=[.!?])\s+", protected) if s.strip()]


def _backed(sentence: str, kinds: list[str], numbers: set[str], entities: set[str], docs: list[Source],
            catalog: Catalog, brand_word: str) -> bool:
    strong = {m.group(0).lower() for m in _STRONG.finditer(sentence)}
    bare_number = not kinds and not entities and not strong
    for doc in docs:
        if bare_number and doc.origin != PERSONAL:
            continue
        lines = doc.lines
        for i in range(len(lines)):
            window = " ".join(lines[i:i + 2])
            if all(CLAIMS[k].search(window) for k in kinds) and numbers <= _numbers(window) \
                    and entities <= _entities(window, catalog, brand_word) \
                    and all(re.search(rf"\b{re.escape(w)}", window, re.I) for w in strong):
                return True
    return False


def check_answer(answer: str, docs: list[Source], catalog: Catalog, brand_name: str = "") -> Checked:
    brand_word = (brand_name.split() or [""])[0].lower()
    has_university_data = bool(catalog.universities or catalog.courses)
    kept: list[str] = []
    reasons: list[str] = []
    for sentence in _split_sentences(answer, catalog):
        if sentence.endswith("?") and not has_university_data and _UNDELIVERABLE_OFFER.search(sentence):
            reasons.append("undeliverable_offer")
            continue
        kinds = [k for k, rx in CLAIMS.items() if rx.search(sentence)]
        if kinds == ["visa_outcome"] and _DISCLAIMER.search(sentence) and not _numbers(sentence):
            kept.append(sentence)   # "we cannot guarantee visa approval" is honest, not a claim
            continue
        numbers = _numbers(sentence)
        if (kinds or numbers or _STRONG.search(sentence)) and not _backed(sentence, kinds, numbers, _entities(sentence, catalog, brand_word), docs,
                                              catalog, brand_word):
            reasons.append(kinds[0] if kinds else "number")
            continue
        kept.append(sentence)
    return Checked(" ".join(kept), dropped=len(reasons), kept=len(kept), reasons=reasons)
