"""
Follow-ups on the UI that is on screen, resolved in code (no LLM).

After a result card is shown, the agent remembers WHAT is on screen (`profile["ui_state"]`: intent, args, ui type +
version). A short refinement such as "only under 20 lakh", "my IELTS is 6.5" or "what about Canada?" then updates the
saved profile and re-runs the SAME intent, so the student gets the same kind of UI with new data. The profile stays the
single source of truth for the filters; `ui_state` only records which UI to re-run.

Deliberately narrow so a wrong parse can't silently corrupt the profile: money needs a currency, a unit or a cue word,
amounts in a different currency than the catalog are ignored (no conversion, nothing invented), and only IELTS scores
are read because the catalog's English minimums are IELTS.
"""
import re
from dataclasses import dataclass, field

from app.schemas.ui_blocks import UI_TYPES
from app.services.education_catalog import Catalog
from app.services.education_ui_registry import INTENTS

MAX_FOLLOWUP_WORDS = 12

# Result intents worth re-running; input cards (choice, slider, form, welcome) never replace what's on screen.
RESULT_INTENTS = ("recommend_country", "country_facts", "compare", "eligibility", "cost_calculator", "profile")
# Intents that take one country, so "what about Canada?" can swap it.
COUNTRY_INTENTS = ("eligibility", "cost_calculator", "country_facts")


# ---- money ----

_UNIT_FACTOR = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "l": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7,
                "k": 1e3, "m": 1e6, "million": 1e6}
_SOUTH_ASIAN_UNITS = {"lakh", "lakhs", "lac", "lacs", "l", "crore", "crores", "cr"}
_CURRENCY = {"$": "USD", "usd": "USD", "us$": "USD", "£": "GBP", "gbp": "GBP", "€": "EUR", "eur": "EUR", "a$": "AUD",
             "aud": "AUD", "c$": "CAD", "cad": "CAD", "npr": "NPR", "nrs": "NPR", "nr": "NPR", "₹": "INR", "inr": "INR",
             "rs": "RS"}  # "Rs" is used for both NPR and INR

_CUR = r"(?:us\$|a\$|c\$|npr|nrs?|inr|usd|gbp|eur|aud|cad|rs|[$£€₹])"
_NUM = r"\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_AMOUNT = re.compile(
    rf"(?:(?P<c1>{_CUR})\.?\s*)?(?P<n>{_NUM})(?:\s*(?P<uw>lakhs?|lacs?|crores?|million)\b|(?P<ua>cr|l|k|m)\b)?"
    r"(?:\s*(?P<c2>npr|nrs?|inr|usd|gbp|eur|aud|cad)\b)?", re.I)
_CUE = re.compile(r"\b(under|below|within|upto|up to|max(?:imum)?|around|about|approx\w*|budget|afford|at most|"
                  r"less than|not more than|only|limit)\b", re.I)


@dataclass(frozen=True)
class Amount:
    value: int
    currency: str | None      # code the student wrote, if any ("RS" = NPR or INR)
    south_asian_unit: bool    # lakh / crore, which implies NPR or INR


def parse_amount(text: str) -> Amount | None:
    """An amount of money the student stated, or None. Years, scores and percentages are never money."""
    strong: Amount | None = None
    bare: list[int] = []
    for m in _AMOUNT.finditer(text):
        number = float(m["n"].replace(",", ""))
        unit = (m["uw"] or m["ua"] or "").lower()
        cur = (m["c1"] or m["c2"] or "").lower()
        if unit or cur:
            value = int(number * _UNIT_FACTOR.get(unit, 1))
            if value > 0 and strong is None:
                strong = Amount(value, _CURRENCY.get(cur), unit in _SOUTH_ASIAN_UNITS)
        elif number >= 1000 and not (number.is_integer() and 1900 <= number <= 2100):
            bare.append(int(number))
    if strong:
        return strong
    if len(bare) == 1 and _CUE.search(text):
        return Amount(bare[0], None, False)
    return None


def catalog_currency_code(symbol: str) -> str:
    return _CURRENCY.get(symbol.strip().lower(), symbol.strip().upper())


def _currency_ok(amount: Amount, catalog_code: str) -> bool:
    """Only apply an amount that is in the catalog's currency; there is no conversion and nothing is guessed."""
    if amount.currency:
        return amount.currency == catalog_code or (amount.currency == "RS" and catalog_code in ("NPR", "INR"))
    if amount.south_asian_unit:
        return catalog_code in ("NPR", "INR")
    return True


# ---- other slots ----

_IELTS = re.compile(r"\bielts\b\D{0,15}?(\d(?:\.\d)?)\b", re.I)
_LEVELS = (("phd", re.compile(r"\b(ph\.?d|doctorate)\b", re.I)),
           ("master", re.compile(r"\b(master'?s?|postgrad\w*|msc)\b", re.I)),
           ("bachelor", re.compile(r"\b(bachelor'?s?|undergrad\w*)\b", re.I)),
           ("foundation", re.compile(r"\bfoundation\b", re.I)))
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december")


def extract_slots(text: str, catalog: Catalog) -> dict:
    """Profile values stated in `text`: budget, IELTS score, study level, intake. Whitelisted fields only."""
    slots: dict = {}
    amount = parse_amount(text)
    if amount and _currency_ok(amount, catalog_currency_code(catalog.currency)):
        slots["budget"] = amount.value
    if m := _IELTS.search(text):
        score = float(m.group(1))
        if 0 <= score <= 9:
            slots["english_test"], slots["english_score"] = "IELTS", score
    for level, rx in _LEVELS:
        if rx.search(text):
            slots["study_level"] = level
            break
    offered = {i.lower(): i for c in catalog.countries for i in c.intakes}
    for month in _MONTHS:
        if month in offered and re.search(rf"\b{month}\b", text, re.I):
            slots["intake"] = offered[month]
            break
    return slots


# ---- UI state ----

def record_ui_state(profile: dict, intent: str, args: dict) -> None:
    """Remember which result UI is on screen (and its type/version), so a follow-up can re-run it."""
    if intent not in RESULT_INTENTS:
        return
    ui = UI_TYPES[INTENTS[intent].block_type]
    profile["ui_state"] = {"intent": intent, "args": {k: v for k, v in args.items() if k != "goal"},
                           "ui": {"type": ui.type, "version": ui.version}}


@dataclass
class FollowUp:
    intent: str
    args: dict
    updates: dict = field(default_factory=dict)   # profile fields to set before re-running


_SWITCH = re.compile(r"^(?:(?:ok(?:ay)?|and|so)[,\s]+)?(?:(?:what|how) about|and)\b", re.I)


def _state(profile: dict, question: str):
    state = profile.get("ui_state")
    q = " ".join(question.split())
    if not state or not q or len(q.split()) > MAX_FOLLOWUP_WORDS or state.get("intent") not in INTENTS:
        return None, q
    return state, q


def resolve_country_switch(question: str, profile: dict, catalog: Catalog) -> FollowUp | None:
    """'what about Canada?' / 'how about Australia' / 'and Canada?' while a one-country UI is on screen: same intent,
    new country. Runs BEFORE the keyword rules, which would otherwise read it as a plain 'about <country>' question."""
    state, q = _state(profile, question)
    if state is None or state["intent"] not in COUNTRY_INTENTS or not _SWITCH.match(q):
        return None
    mentioned = catalog.find_in_text(q)
    if len(mentioned) != 1:
        return None
    return FollowUp(state["intent"], {**(state.get("args") or {}), "country": mentioned[0]})


def resolve_refinement(question: str, profile: dict, catalog: Catalog) -> FollowUp | None:
    """'only under $30k' / 'my IELTS is 7' while a UI that uses that value is on screen: update the profile, re-run the
    same intent. Runs AFTER the keyword rules, so a message with its own explicit intent keeps that intent."""
    state, q = _state(profile, question)
    if state is None:
        return None
    slots = extract_slots(q, catalog)
    if slots and set(INTENTS[state["intent"]].input_fields) & set(slots):
        return FollowUp(state["intent"], dict(state.get("args") or {}), slots)
    return None


def resolve_followup(question: str, profile: dict, catalog: Catalog) -> FollowUp | None:
    """Both stages in order (the agent runs them on either side of the keyword rules)."""
    return resolve_country_switch(question, profile, catalog) or resolve_refinement(question, profile, catalog)
