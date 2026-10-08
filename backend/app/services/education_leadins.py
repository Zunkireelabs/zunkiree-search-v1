"""
The one-line sentence that introduces a card, written by code from the card itself.

Why not the LLM: a model asked to introduce a card it cannot see well enough sometimes contradicts it ("Canada matches your
profile" over a card where every country needs review), offers things we don't have ("explore universities or programs") or
twists a fact. A sentence built from the card's own data can't do any of that, and it costs no LLM call, so card replies
arrive in a fraction of the time.

English only: a message in another language keeps the LLM-written lead-in (which follows the student's language).
Every sentence is neutral: no "best", no percentages, no promise that anyone will contact the student, no mention of
universities or programs, and nothing the card itself doesn't show.
"""
import re

from app.schemas.ui_blocks import UIBlock
from app.services.education_catalog import Catalog

# Introducing an answer built from the tenant's own knowledge base, and the honest "not there" reply.
KB_FOUND = "Here's what I found in our materials."
KB_MISS = "I don't have that detail yet. A counselor can help you with it."

_CHOICE = {
    "countries": "Let's start with where you'd like to study.",
    "study_level": "Got it. Next, what level do you want to study?",
    "intake": "Almost there. When would you like to start?",
    "focus_country": "Which country would you like me to look at?",
}


def _label(catalog: Catalog, country_id) -> str | None:
    country = catalog.get(country_id) if isinstance(country_id, str) else None
    return country.label if country else None


def _names(labels: list[str]) -> str:
    return labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]


def _recommendation(block: UIBlock) -> str:
    top = block.data["items"][0]
    if top["tier"] == "strong":
        return f"{top['label']} lines up strongly with what you've told me. Here's how all the countries compare."
    if top["tier"] == "good":
        return f"{top['label']} is a good fit so far. Here's how all the countries compare."
    if top["tier"] == "possible":
        return f"Nothing is a clear fit yet; {top['label']} comes closest. Here's how the countries compare."
    return "I couldn't find a clear fit with what you've shared so far. The reasons for each country are below."


def leadin_for(intent: str, args: dict, block: UIBlock, catalog: Catalog, brand_name: str) -> str | None:
    """The sentence to show with this card, or None when there isn't a safe one (the caller then asks the LLM)."""
    text = _sentence(intent, args, block, catalog, brand_name)
    # a label such as "U.K." already ends in a full stop: never print "U.K.."
    return re.sub(r"(?<=\.)\.(?!\.)", "", text) if text else text


def _sentence(intent: str, args: dict, block: UIBlock, catalog: Catalog, brand_name: str) -> str | None:
    if intent == "welcome":
        return f"Hi! I'm {brand_name}'s study-abroad assistant. Where would you like to start?"
    if intent == "choice":
        return _CHOICE.get(block.data.get("field"))
    if intent == "budget":
        return "Next, set your yearly budget (tuition plus living costs)."
    if intent == "recommend_country":
        return _recommendation(block)
    if intent == "profile":
        return "Here's what I know about you so far."
    if intent == "lead_form":
        return "Please fill in your details below."
    if intent == "compare":
        return f"Here's {_names([c['label'] for c in block.data['columns']])} side by side."
    country = _label(catalog, args.get("country"))
    if country is None:
        return None
    if intent == "country_facts":
        return f"Here are the quick facts for {country}."
    if intent == "eligibility":
        return f"Here's how your scores compare with {country}'s requirements."
    if intent == "cost_calculator":
        return f"Here's a cost estimate for {country}. Drag the sliders to adjust it."
    return None
