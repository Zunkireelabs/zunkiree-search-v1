"""
The fixed map: question type -> tool -> block type (+ title).

This is the consistency guarantee. One intent maps to exactly one tool, and each
tool emits exactly one block type with a registry-owned title, so "which countries
fit my profile?" renders the same kind of block every time it's asked. The LLM
never chooses a block's shape or title.

`detect_intent` is deterministic (keyword rules) and runs BEFORE the LLM, so the
core questions never depend on the model remembering a prompt rule.
"""
import re
from dataclasses import dataclass

from app.services.education_catalog import Catalog


@dataclass(frozen=True)
class IntentSpec:
    intent: str
    tool: str
    block_type: str
    title: str  # may contain {placeholders} filled by the tool (e.g. country label)
    # Profile fields that feed this block. A change to any of them is what
    # makes a re-shown block "updated"; unrelated profile changes don't.
    input_fields: tuple[str, ...] = ()


INTENTS: dict[str, IntentSpec] = {s.intent: s for s in [
    IntentSpec("country_matches", "show_country_matches", "match_cards",
               "Countries that match your profile",
               ("budget", "english_score", "academic_score", "intake")),
    IntentSpec("country_facts", "show_country_facts", "info_card", "{country} quick facts"),
    IntentSpec("compare", "compare_countries", "comparison_table", "{countries}"),
    IntentSpec("eligibility", "check_eligibility", "eligibility_meter", "{country} eligibility",
               ("english_score", "academic_score")),
    IntentSpec("profile", "show_profile", "profile_summary", "What I know about you",
               ("countries", "study_level", "field_of_study", "budget", "intake",
                "english_test", "english_score", "academic_score", "focus_country")),
    IntentSpec("lead_form", "show_lead_form", "lead_form", "Talk to a counselor"),
    IntentSpec("budget", "show_budget_slider", "range_slider", "Your yearly budget (tuition + living)",
               ("budget",)),
    # Guided questions: one tool, `kind` picks which question.
    IntentSpec("choice", "show_choice", "choice_cards", "{question}"),
    IntentSpec("welcome", "show_welcome", "journey_cards", "How can I help you today?"),
    IntentSpec("cost_calculator", "show_cost_calculator", "cost_calculator", "{country} cost calculator"),
]}

TOOL_TO_INTENT: dict[str, str] = {s.tool: s.intent for s in INTENTS.values()}

CHOICE_QUESTIONS = {
    "countries": ("Which countries are you interested in?", True, "Pick one or more"),
    "study_level": ("What level do you want to study?", False, None),
    "intake": ("When do you want to start?", False, None),
    # Single country for a follow-up like eligibility or costs (sets focus_country, not the shortlist).
    "country_one": ("Which country do you want to look at?", False, None),
}

# Welcome tiles: (id, icon, title, description, needs_catalog). Tiles that need country data are
# hidden for a tenant without a catalog; nothing is offered that can't be delivered.
JOURNEY = [
    ("find", "🌍", "Find the right country", "Match countries to your budget and scores", True),
    ("eligibility", "🎓", "Check my eligibility", "See if you meet a country's requirements", True),
    ("costs", "💰", "Estimate my costs", "Tuition and living costs in a live calculator", True),
    ("apply", "📝", "How to apply", "The application process, step by step", False),
    ("counselor", "💬", "Talk to a counselor", "Get personal help from our team", False),
]

APPLY_QUERY = "What is the process to apply?"

# Fixed option sets for non-country questions (not facts about a tenant, just answer choices).
STUDY_LEVELS = [("foundation", "Foundation"), ("bachelor", "Bachelor's"),
                ("master", "Master's"), ("phd", "PhD")]


def _rx(*patterns: str) -> re.Pattern:
    return re.compile("|".join(patterns), re.I)


_COMPARE = _rx(r"\bvs\.?\b", r"\bversus\b", r"\bcompare\b", r"\bcomparison\b", r"\bor\b.+\bwhich\b", r"\bbetter\b")
_MATCHES = _rx(r"which countr", r"what countr", r"best countr", r"suitable countr", r"countries? (for|that|suit|fit|match)",
               r"where (should|can|do) i (study|go)", r"fit my profile", r"match my profile", r"applicable")
_ELIGIBILITY_STRICT = _rx(r"eligib", r"\bqualify\b", r"\bchances?\b")
_ELIGIBILITY_BROAD = _rx(r"eligib", r"\bqualify\b", r"\bchances?\b", r"can i (get|apply|study)", r"meet the requirement")
_COST = _rx(r"\bcost\b", r"\bfees?\b", r"\bbudget\b", r"how much", r"afford", r"\bexpens", r"tuition")
_ABOUT_COMPANY = _rx(r"\badmizz\b", r"\byou(r)?\b", r"\bservices?\b", r"\bconsult", r"\bcounsel")
_PROFILE = _rx(r"my profile", r"about me", r"what do you know", r"my details", r"summary of")
_COUNSELOR = _rx(r"counsel+or", r"talk to (a |an )?(person|human|someone|agent)", r"call me", r"contact me",
                 r"speak (to|with)", r"book (a )?(session|consult|appointment)", r"apply now", r"help me apply")
_START = _rx(r"study abroad", r"want to study", r"get started", r"^start$", r"help me (choose|find|pick)")
_FACTS = _rx(r"tell me (more )?about", r"\babout\b", r"info(rmation)? (on|about)", r"quick facts", r"explore")
_GREETING = _rx(r"^(hi+|hello+|hey+|hola|namaste|namaskar|greetings|good (morning|afternoon|evening))\b[\s!.,?]*$")


def known_country(profile: dict | None, catalog: Catalog) -> str | None:
    """The one country we can assume the student means: the one in focus, else their only shortlisted one."""
    if not profile:
        return None
    focus = profile.get("focus_country")
    if focus and catalog.get(focus):
        return focus
    picked = [c for c in profile.get("countries") or [] if catalog.get(c)]
    return picked[0] if len(picked) == 1 else None


def country_goal(goal: str, mentioned: list[str], profile: dict | None, catalog: Catalog) -> tuple[str, dict] | None:
    """eligibility / costs need ONE country: use the one mentioned or known, else ask which."""
    intent = {"eligibility": "eligibility", "costs": "cost_calculator"}[goal]
    country = mentioned[0] if len(mentioned) == 1 else known_country(profile, catalog)
    if country:
        return intent, {"country": country}
    if catalog.countries:
        return "choice", {"kind": "country_one", "goal": goal}
    return None


def journey_intent(journey: str, profile: dict | None, catalog: Catalog) -> tuple[str, dict] | None:
    """A tapped welcome tile -> where it leads. 'kb_shape' means: build an answer component from the knowledge base."""
    if journey == "find":
        return ("choice", {"kind": "countries"}) if catalog.countries else None
    if journey in ("eligibility", "costs"):
        return country_goal(journey, [], profile, catalog)
    if journey == "apply":
        return "kb_shape", {"shape": "process", "query": APPLY_QUERY}
    if journey == "counselor":
        return "lead_form", {}
    return None


def detect_intent(question: str, catalog: Catalog, profile: dict | None = None) -> tuple[str, dict] | None:
    """
    Deterministic question -> (intent, args), or None to continue to the knowledge-base shapes / the LLM.
    Order matters: more specific intents first.
    """
    q = question.strip()
    mentioned = catalog.find_in_text(q)

    if _GREETING.match(q):
        return "welcome", {}
    if _COUNSELOR.search(q):
        return "lead_form", {}
    # "which countries fit my profile" contains "my profile": the matches rule must win.
    if _MATCHES.search(q):
        return "country_matches", {}
    if _PROFILE.search(q):
        return "profile", {}
    if len(mentioned) >= 2 and _COMPARE.search(q):
        return "compare", {"countries": mentioned[:3]}
    if (_ELIGIBILITY_BROAD if len(mentioned) == 1 else _ELIGIBILITY_STRICT).search(q):
        goal = country_goal("eligibility", mentioned, profile, catalog)
        if goal:
            return goal
    if _COST.search(q) and not _ABOUT_COMPANY.search(q):
        goal = country_goal("costs", mentioned, profile, catalog)
        if goal:
            return goal
    if len(mentioned) == 1 and _FACTS.search(q):
        return "country_facts", {"country": mentioned[0]}
    if _START.search(q):
        return "choice", {"kind": "countries"}
    return None
