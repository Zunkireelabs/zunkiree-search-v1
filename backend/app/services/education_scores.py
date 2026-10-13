"""Scores with their unit.

A bare number is not a score: 3.64 is a GPA out of 4, 72 is a percentage, 90 is a TOEFL score. The catalog's minimums are an
IELTS band and a percentage, so a number is only compared when its unit says it is comparable. Scores are read from the
student's own words in code (the AI sometimes asks "check eligibility" before it saves what the student just said, and drops
the word "gpa" when it does save), and a GPA is converted by one explicit estimate rule that the card says is an estimate.
"""
import re

# GPA -> percentage. THE rule, in one place. There is no official conversion (universities and countries differ), so this is a
# plain proportion and every result that uses it says "estimated". Replace this function to use Admizz's own table.
def gpa_to_percent(gpa: float, scale: float) -> float:
    return gpa / scale * 100


GPA_SCALES = (4, 5, 10)
PERCENT_RANGE = (10, 100)     # a percentage at or below 10 is, in practice, a GPA that was saved in the wrong field
_TEST_RANGES = {"IELTS": (0, 9), "TOEFL": (0, 120), "PTE": (10, 90), "Duolingo": (10, 160)}
_TEST_NAMES = {"ielts": "IELTS", "toefl": "TOEFL", "pte": "PTE", "duolingo": "Duolingo"}


def infer_gpa_scale(gpa: float) -> int | None:
    """4.0 scale up to 4, 10-point scale above 5; between them it could be either, so the caller must not guess."""
    if 0 < gpa <= 4:
        return 4
    if 5 < gpa <= 10:
        return 10
    return None


def academic_percent(profile: dict) -> tuple[float | None, tuple[float, float] | None]:
    """(percentage, None) for a real percentage; (estimate, (gpa, scale)) for a converted GPA; (None, None) otherwise."""
    score = profile.get("academic_score")
    if score is not None and PERCENT_RANGE[0] < score <= PERCENT_RANGE[1]:
        return score, None
    gpa, scale = profile.get("academic_gpa"), profile.get("academic_gpa_scale")
    if gpa and scale:
        return gpa_to_percent(gpa, scale), (gpa, scale)
    return None, None


def ielts_comparable(profile: dict) -> float | None:
    """The English score, only if it can be held against an IELTS minimum (IELTS, or a test the student did not name)."""
    score, test = profile.get("english_score"), (profile.get("english_test") or "").strip().lower()
    if score is None or (test and not test.startswith("ielts")):
        return None
    return score


# --- reading scores from free text -----------------------------------------------------------------------------------

_NUM = r"(\d{1,3}(?:\.\d+)?)"
_TEST = r"(ielts|toefl|pte|duolingo)"
_I = re.IGNORECASE

# A question or a requirement is not the student's own score ("UK requires ielts 6.5", "which countries need 65%?").
_NOT_A_STATEMENT = re.compile(r"\?|\b(?:requires?|required|requirements?|minimum|min|need(?:s|ed)?|cut-?off|at least|what|which|how|should|must)\b", _I)
_NOT_ACADEMIC = re.compile(r"\b(?:budget|scholarship|discount|fees?|tuition|deposit|loan)\b", _I)
_ACADEMIC_WORD = re.compile(r"\b(?:percent|percentage|marks|result|scored|secured|academic|aggregate|grade)\b", _I)

_ENGLISH = [
    re.compile(rf"\b{_NUM}\s+(?:is|was)\s+my\s+(?:{_TEST}|english)\b", _I),
    re.compile(rf"\bmy\s+(?:{_TEST}|english)(?:\s+(?:test|exam))?(?:\s+(?:score|band|result))?\s*(?:is|was|:|=)?\s*{_NUM}\b", _I),
    re.compile(rf"\b(?:scored|got|have|had|achieved|secured)\s+{_NUM}\s*(?:in|on|for)?\s*(?:my\s+)?(?:{_TEST}|english)\b", _I),
]
_ENGLISH_NUM_FIRST = (0, 2)   # the patterns where the number comes before the test name

_GPA = [
    re.compile(rf"\bc?gpa\b\s*(?:score|is|was|of|:|=)?\s*{_NUM}(?:\s*(?:/|out of)\s*{_NUM})?", _I),
    re.compile(rf"\b{_NUM}\s*(?:(?:/|out of)\s*{_NUM})?\s*c?gpa\b", _I),
]
_PERCENT = [
    re.compile(rf"\b{_NUM}\s*(?:%|percent\b|percentage\b)", _I),
    re.compile(rf"\b(?:percentage|marks|aggregate|result)\s*(?:score)?\s*(?:is|was|:|=)?\s*{_NUM}\b", _I),
]


def _english(text: str) -> dict:
    for i, rx in enumerate(_ENGLISH):
        if m := rx.search(text):
            number, test = (m.group(1), m.group(2)) if i in _ENGLISH_NUM_FIRST else (m.group(2), m.group(1))
            score = float(number)
            name = _TEST_NAMES.get((test or "").lower())
            low, high = _TEST_RANGES[name] if name else _TEST_RANGES["IELTS"]   # test not named: only an IELTS-sized number
            if not low < score <= high:
                return {}
            out = {"english_test": name} if name else {}
            return {**out, "english_score": int(score) if score.is_integer() else score}
    return {}


def _gpa(text: str) -> dict:
    for rx in _GPA:
        if m := rx.search(text):
            gpa = float(m.group(1))
            scale = float(m.group(2)) if m.group(2) else None
            scale = int(scale) if scale in GPA_SCALES else (None if scale else infer_gpa_scale(gpa))
            if scale and 0 < gpa <= scale:
                return {"academic_gpa": int(gpa) if gpa.is_integer() else gpa, "academic_gpa_scale": scale}
            return {}
    return {}


def _percent(text: str) -> dict:
    if _NOT_ACADEMIC.search(text) or not _ACADEMIC_WORD.search(text):
        return {}
    for rx in _PERCENT:
        if m := rx.search(text):
            score = float(m.group(1))
            if PERCENT_RANGE[0] < score <= PERCENT_RANGE[1]:
                return {"academic_score": int(score) if score.is_integer() else score}
            return {}
    return {}


def extract_scores(text: str) -> dict:
    """Scores the student stated about themselves in `text`, as profile updates. Empty for questions and requirements."""
    if not text or _NOT_A_STATEMENT.search(text):
        return {}
    return {**_english(text), **_gpa(text), **_percent(text)}
