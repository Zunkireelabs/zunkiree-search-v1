"""
Compositions: a result card plus the blocks that make it useful, in a fixed order per intent.

    recommend_country -> profile summary, match cards, next-step buttons
    compare / eligibility / country_facts / cost_calculator / profile -> the card, next-step buttons

The same intent and the same state always produce the same blocks. Every part is built by the existing deterministic
tools and validated like any other block; nothing here is written by the LLM.

Next-step buttons (the registered `quick_chips` block) come from a CLOSED set of ids, resolved by `chip_intent`:
    matches | profile | budget | lead | compare:a+b | eligibility:c | cost:c | facts:c
A button is offered only if the card it leads to can actually be built right now (checked by running the real builder on
a throwaway copy of the profile), so nothing is offered that can't be delivered. At most MAX_CHIPS buttons.
"""
from app.schemas.ui_blocks import UIBlock, build_block
from app.services.education_catalog import Catalog
from app.services.education_followup import COUNTRY_INTENTS
from app.services.education_tools import execute_education_tool, tool_for_intent

MAX_CHIPS = 3

# part names: "primary" = the block the intent's tool built; "profile" = the profile summary; "next_steps" = the buttons
COMPOSITIONS: dict[str, tuple[str, ...]] = {
    "recommend_country": ("profile", "primary", "next_steps"),
    "compare": ("primary", "next_steps"),
    "eligibility": ("primary", "next_steps"),
    "country_facts": ("primary", "next_steps"),
    "cost_calculator": ("primary", "next_steps"),
    "profile": ("primary", "next_steps"),
}


# ---- the closed set of buttons ----

_SIMPLE_CHIPS = {
    "matches": ("recommend_country", "Which countries fit me?"),
    "profile": ("profile", "What do you know about me?"),
    "budget": ("budget", "Update my budget"),
    "lead": ("lead_form", "Talk to a counselor"),
}
_COUNTRY_CHIPS = {  # chip kind -> (intent, label template)
    "eligibility": ("eligibility", "Check my eligibility for {c}"),
    "cost": ("cost_calculator", "Estimate costs for {c}"),
    "facts": ("country_facts", "Quick facts: {c}"),
}


def chip_intent(chip_id: str, catalog: Catalog) -> tuple[str, dict] | None:
    """The (intent, args) a button id stands for, or None if the id is not one of the closed set or names an unknown country."""
    if chip_id in _SIMPLE_CHIPS:
        return _SIMPLE_CHIPS[chip_id][0], {}
    kind, _, rest = chip_id.partition(":")
    if kind in _COUNTRY_CHIPS and catalog.get(rest):
        intent, _label = _COUNTRY_CHIPS[kind]
        return intent, {"country": rest}
    if kind == "compare":
        ids = rest.split("+")
        if 2 <= len(ids) <= 3 and len(set(ids)) == len(ids) and all(catalog.get(i) for i in ids):
            return "compare", {"countries": ids}
    return None


def chip_label(chip_id: str, catalog: Catalog) -> str:
    if chip_id in _SIMPLE_CHIPS:
        return _SIMPLE_CHIPS[chip_id][1]
    kind, _, rest = chip_id.partition(":")
    if kind == "compare":
        return "Compare " + " and ".join(catalog.get(i).label for i in rest.split("+"))
    return _COUNTRY_CHIPS[kind][1].format(c=catalog.get(rest).label)


def _chips_block(chip_ids: list[str], catalog: Catalog) -> UIBlock:
    chips = [{"id": c, "label": chip_label(c, catalog)} for c in chip_ids]
    return build_block("quick_chips", {"chips": chips}, fallback_text="Next: " + "; ".join(c["label"] for c in chips) + ".")


def counselor_block(catalog: Catalog) -> UIBlock:
    """Shown when the knowledge base has no answer: the one useful thing left to offer."""
    return _chips_block(["lead"], catalog)


# ---- which buttons follow which card ----

def _country_id(catalog: Catalog, value) -> str | None:
    if isinstance(value, str) and catalog.get(value):
        return value
    found = catalog.find_in_text(str(value or ""))
    return found[0] if found else None


def normalized_args(intent: str, raw: dict, catalog: Catalog) -> dict:
    """Arguments as catalog ids. A tool called by the LLM passes names and aliases ("Australia", "UK"); the saved state and
    the buttons need ids. Anything that doesn't resolve is dropped."""
    if intent in COUNTRY_INTENTS:
        country = _country_id(catalog, raw.get("country"))
        return {"country": country} if country else {}
    if intent == "compare":
        ids: list[str] = []
        for value in raw.get("countries") or []:
            cid = _country_id(catalog, value)
            if cid and cid not in ids:
                ids.append(cid)
        return {"countries": ids[:3]}
    return {}


def _candidates(intent: str, args: dict, primary: UIBlock, catalog: Catalog) -> list[str]:
    if intent == "recommend_country":
        fits = [i["id"] for i in primary.data["items"] if i["tier"] != "needs_review"]
        top = fits[0] if fits else None
        out = [f"compare:{fits[0]}+{fits[1]}"] if len(fits) >= 2 else []
        if top:
            out += [f"eligibility:{top}", f"cost:{top}"]
        return out + ["budget"]
    if intent == "compare":
        first = primary.data["columns"][0]["id"]
        return [f"eligibility:{first}", f"cost:{first}", "lead"]
    country = _country_id(catalog, args.get("country"))
    if intent == "eligibility" and country:
        return [f"cost:{country}", "matches", "lead"]
    if intent == "country_facts" and country:
        return [f"eligibility:{country}", f"cost:{country}", "matches"]
    if intent == "cost_calculator" and country:
        return [f"eligibility:{country}", f"facts:{country}", "lead"]
    if intent == "profile":
        return ["matches", "budget", "lead"]
    return []


def _can_build(resolved: tuple[str, dict], profile: dict, catalog: Catalog) -> bool:
    intent, args = resolved
    probe = {k: v for k, v in profile.items() if k != "shown"}      # a throwaway copy: no cache entries leak into the real profile
    return execute_education_tool(tool_for_intent(intent), dict(args), probe, catalog).block is not None


def next_steps(intent: str, args: dict, primary: UIBlock, profile: dict, catalog: Catalog) -> UIBlock | None:
    chosen: list[str] = []
    for chip_id in _candidates(intent, args, primary, catalog):
        resolved = chip_intent(chip_id, catalog)
        if resolved and _can_build(resolved, profile, catalog):
            chosen.append(chip_id)
        if len(chosen) == MAX_CHIPS:
            break
    return _chips_block(chosen, catalog) if chosen else None


# ---- composing ----

def compose(intent: str, args: dict, primary: UIBlock, profile: dict, catalog: Catalog) -> list[UIBlock]:
    """The blocks to show for this intent, in order, `primary` included. An intent with no recipe shows just `primary`."""
    blocks: list[UIBlock] = []
    for part in COMPOSITIONS.get(intent, ("primary",)):
        if part == "primary":
            blocks.append(primary)
        elif part == "profile":
            summary = execute_education_tool("show_profile", {}, profile, catalog).block
            if summary:
                blocks.append(summary)
        elif part == "next_steps":
            steps = next_steps(intent, args, primary, profile, catalog)
            if steps:
                blocks.append(steps)
    return blocks
