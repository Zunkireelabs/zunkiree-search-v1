"""Reads ONE Admizz university page (https://admizzeducation.com/explore-universities/<country>/<slug>) into University and Course records.

Pure parsing: HTML text in, records and warnings out. No network, no files, no database. What a page states is copied; nothing is
inferred or converted, and a value the page does not state stays None (with a warning when the page states something we cannot read).
Every record is website text that nobody has verified: the page's own "last verified" date is kept as provenance, not as proof.

Tuition: the page says "total" or "per year" next to the amount. `Course.tuition_per_year` is filled from "per year" as is, and from
"total" only when the course lasts one year or less (then the two are the same number). A multi-year "total" is NOT divided (that would
be a guess): it is kept as `tuition_total`. Any wording beyond a plain figure ("from £X total · then master's year £Y") is kept
verbatim in `tuition_note`.
"""
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from app.services.education_catalog_models import Course, University
from app.services.money import Money

LEVELS = {"Foundation": "foundation", "Undergraduate": "bachelor", "Postgraduate": "master"}
# The page lists English and academic requirements under Undergraduate/Postgraduate; a foundation course belongs to the first.
REQUIREMENT_HEADING = {"foundation": "Undergraduate", "bachelor": "Undergraduate", "master": "Postgraduate"}
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")

_AMOUNT = re.compile(r"£\s*([\d,]+)")
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(year|yr|month|mo)s?\b", re.IGNORECASE)
_FEE = re.compile(r"(from\s+)?£\s*([\d,]+)\s+(per year|total)\b\s*(.*)", re.IGNORECASE | re.DOTALL)
_PERCENT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
_IELTS = re.compile(r"(\d(?:\.\d)?)\s*overall", re.IGNORECASE)
_VERIFIED = re.compile(r"\d{4}-\d{2}-\d{2}")
_SECTION_END = ("Scholarships", "Academic requirements")


@dataclass
class ParsedUniversity:
    university: University
    courses: list[Course] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    last_verified: str | None = None          # the page's own statement, e.g. "2026-10-07"
    levels: list[str] = field(default_factory=list)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return [line for line in (raw.strip() for raw in soup.get_text("\n").split("\n")) if line]


def _months_of(parts: list[str]) -> list[str]:
    text = " ".join(parts)
    return [m for m in MONTHS if re.search(rf"\b{m}\b", text, re.IGNORECASE)]


def _duration_months(text: str) -> int | None:
    m = _DURATION.search(text)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).lower()
    months = value * 12 if unit in ("year", "yr") else value
    return int(round(months)) if months > 0 else None


def _block(lines: list[str], heading: str, stop: tuple[str, ...]) -> list[str]:
    """The lines under `heading` (the first match) until the next heading in `stop`."""
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return []
    out: list[str] = []
    for line in lines[start:]:
        if line in stop:
            break
        out.append(line)
    return out


def _level_block(block: list[str], level_heading: str) -> list[str]:
    """Within a requirements block, the lines for one study level ('Undergraduate' / 'Postgraduate')."""
    try:
        start = block.index(level_heading) + 1
    except ValueError:
        return []
    out: list[str] = []
    for line in block[start:]:
        if line in LEVELS:
            break
        out.append(line)
    return out


def _requirements(lines: list[str], warnings: list[str]) -> dict[str, dict]:
    """{'Undergraduate'|'Postgraduate': {'ielts': float|None, 'percent': float|None}} from the page's requirement sections.

    A value is taken only when the page states exactly one of it; two different entry routes (terms, years) are not merged."""
    academic = _block(lines, "Academic requirements", ("English language", "Gap", "Tuition fees"))
    english = _block(lines, "English language", ("Gap", "Tuition fees", "Scholarship"))
    out: dict[str, dict] = {}
    for heading in ("Undergraduate", "Postgraduate"):
        rows = [r for r in _level_block(academic, heading) if r != "Admission criteria for Nepali students, by study level."]
        percents = {float(p) for r in rows for p in _PERCENT.findall(r)}
        percent = percents.pop() if len(rows) == 1 and len(percents) == 1 else None
        if rows and percent is None:
            warnings.append(f"{heading}: academic requirement not read as one percentage ({len(rows)} line(s)); left empty")
        ielts_values: set[float] = set()
        eng = _level_block(english, heading)
        for i, line in enumerate(eng):
            if line.upper().startswith("IELTS") and i + 1 < len(eng):
                m = _IELTS.search(eng[i + 1])
                if m:
                    ielts_values.add(float(m.group(1)))
        ielts = ielts_values.pop() if len(ielts_values) == 1 else None
        if eng and any(l.upper().startswith("IELTS") for l in eng) and ielts is None:
            warnings.append(f"{heading}: IELTS not read as one score; left empty")
        out[heading] = {"ielts": ielts, "percent": percent}
    return out


def _parse_courses(lines: list[str], slug: str, source: str, requirements: dict[str, dict], warnings: list[str]) -> list[Course]:
    start = next((i for i, l in enumerate(lines) if l.startswith("Tuition shown is the published fee")), None)
    if start is None:
        coming_soon = any(l.startswith("Course list coming soon") for l in lines)
        warnings.append("course list not published yet (the page says 'coming soon')" if coming_soon else "no course list found")
        return []
    end = next((i for i in range(start, len(lines)) if lines[i] in _SECTION_END), len(lines))
    region = lines[max(start - 2, 0):end]
    courses: list[Course] = []
    seen: dict[str, int] = {}
    level: str | None = None
    i = 0
    while i < len(region):
        line = region[i]
        if line in LEVELS and i + 1 < len(region) and region[i + 1] == "courses":
            level = LEVELS[line]
            i += 2
            continue
        if i + 1 < len(region) and region[i + 1] == "Duration" and level is not None:
            name = line.strip()
            j = i + 2
            take: list[str] = []
            while j < len(region) and region[j] != "Enquire about this course":
                take.append(region[j])
                j += 1
            i = j + 1
            course = _one_course(name, take, level, slug, source, requirements, seen, warnings)
            if course:
                courses.append(course)
            continue
        i += 1
    return courses


def _one_course(name: str, take: list[str], level: str, slug: str, source: str, requirements: dict[str, dict],
                seen: dict[str, int], warnings: list[str]) -> Course | None:
    """`take` is the lines between 'Duration' and 'Enquire about this course': duration, 'Tuition', amount, basis, 'Intake', months."""
    try:
        t, k = take.index("Tuition"), take.index("Intake")
    except ValueError:
        warnings.append(f"{name}: course card not readable; skipped")
        return None
    duration = _duration_months(" ".join(take[:t]))
    amount_m = _AMOUNT.search(" ".join(take[t + 1:k]))
    basis = " ".join(take[t + 1:k]).lower()
    intakes = _months_of(take[k + 1:])
    wording = " ".join(take[t + 1:k]).strip()
    tuition: Money | None = None
    total: Money | None = None
    note: str | None = None
    fee = _FEE.match(wording)
    if fee is None:
        note = wording or None
        warnings.append(f"{name}: no tuition amount (the page says '{wording}')" if not _AMOUNT.search(wording)
                        else f"{name}: tuition wording not read ('{wording}'); kept as a note only")
    elif fee.group(1):
        note = wording            # "from £X ...": a minimum, not this course's fee; the page's own words are kept
    else:
        amount, basis, rest = int(fee.group(2).replace(",", "")), fee.group(3).lower(), fee.group(4).lstrip("· ").strip()
        if basis == "per year" or (duration is not None and duration <= 12):
            tuition = Money(amount, "GBP")
        else:
            total = Money(amount, "GBP")                      # a multi-year total: kept as a total, never divided
        note = rest or None   # anything after the figure, e.g. "£13,000 after £3,000 scholarship"
    req = requirements.get(REQUIREMENT_HEADING[level], {})
    base = f"{slug}--{slugify(name)}"
    seen[base] = seen.get(base, 0) + 1
    course_id = base if seen[base] == 1 else f"{base}-{seen[base]}"
    try:
        return Course(id=course_id, university_id=slug, name=name, level=level, duration_months=duration, tuition_per_year=tuition,
                      tuition_total=total, tuition_note=note, intakes=intakes, ielts_min=req.get("ielts"),
                      academic_min_percent=req.get("percent"), source=source)
    except ValueError as e:
        warnings.append(f"{name}: rejected ({e})")
        return None


def parse_university_page(html: str, *, slug: str, country_id: str, url: str) -> ParsedUniversity | None:
    """The university and its courses, or None when the page is not a university page at all."""
    lines = _lines(html)
    title = BeautifulSoup(html, "html.parser").find("h1")
    name = title.get_text(" ", strip=True) if title else ""
    if not name or "Talk to a Counsellor" not in lines:      # not "Fees from": a university with no published fee has no such line
        return None
    warnings: list[str] = []
    campus = _block(lines, "Campus locations", ("View on map",))
    city = campus[0].split(",")[0].strip() if campus else None
    intake_block = _block(lines, "Intakes & deadlines", ("Showing intakes currently open through Admizz. Other intakes may be available — ask a counsellor.",
                                                          "Campus locations"))
    intakes = _months_of(intake_block)
    verified = None
    for i, l in enumerate(lines):
        if l.startswith("Information last verified on") and i + 1 < len(lines) and _VERIFIED.fullmatch(lines[i + 1]):
            verified = lines[i + 1]
            break
    if verified is None:
        warnings.append("page states no 'last verified' date")
    requirements = _requirements(lines, warnings)
    source = f"Admizz website {url}" + (f" (page says last verified {verified}; not verified by us)" if verified else " (unverified)")
    courses = _parse_courses(lines, slug, url, requirements, warnings)
    stated = next((int(lines[i + 1]) for i, l in enumerate(lines) if l == "Courses" and i + 1 < len(lines) and lines[i + 1].isdigit()), None)
    if stated is not None and stated != len(courses):
        warnings.append(f"page states {stated} courses, {len(courses)} were read")
    university = University(id=slug, name=name, country_id=country_id, city=city, website=url, intakes=intakes, source=source)
    return ParsedUniversity(university=university, courses=courses, warnings=warnings, last_verified=verified,
                            levels=sorted({c.level for c in courses}))
