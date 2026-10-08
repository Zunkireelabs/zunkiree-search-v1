"""
Tools for the education agent. Each tool builds one validated UI block from the
tenant's catalog + the student's profile (deterministic Python, never LLM output)
and returns a short message the LLM uses to write a one-line lead-in.

Result blocks (matches / facts / compare / eligibility / profile) go through the
block cache: same question + unchanged inputs -> the identical block again.
If the inputs changed, the same block type is rebuilt with new content and a
"changed_because" note. Input blocks (choice / slider / form) are never cached
because they reflect the student's current selection.
"""
import logging
from dataclasses import dataclass, field
from typing import Callable

from app.schemas.ui_blocks import BlockValidationError, UIBlock, build_block, is_current, upgrade_stored_block
from app.services.education_catalog import Catalog, CountryRecord, check_eligibility, score_countries
from app.services.education_profile import (
    FIELD_LABELS, apply_updates, missing_slots, profile_hash, profile_rows, snapshot,
)
from app.services.money import format_money_range
from app.services.education_ui_registry import (
    CHOICE_QUESTIONS, INTENTS, JOURNEY, STUDY_LEVELS, TOOL_TO_INTENT, IntentSpec,
)

logger = logging.getLogger("zunkiree.education_tools")

_PROFILE_FIELDS_SCHEMA = {
    "countries": {"type": "array", "items": {"type": "string"},
                  "description": "Destination countries the student wants (names or ids)."},
    "study_level": {"type": "string", "description": "foundation, bachelor, master, or phd"},
    "field_of_study": {"type": "string", "description": "Subject area, e.g. 'IT', 'Nursing', 'Business'"},
    "intake": {"type": "string", "description": "Preferred start, e.g. 'September', 'February'"},
    "budget": {"type": "number", "description": "Yearly budget (tuition + living), a plain number"},
    "english_test": {"type": "string", "description": "IELTS, PTE, TOEFL, Duolingo, ..."},
    "english_score": {"type": "number", "description": "The student's English test score"},
    "academic_score": {"type": "number", "description": "Latest academic result as a percentage"},
}


def _tool(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
    }}


EDUCATION_TOOLS = [
    _tool("update_profile",
          "Save facts the student just told you in their own words (e.g. 'my IELTS is 6.5', 'I want to do a master's "
          "in the UK'). Call it whenever they state one of these facts. Does not show anything.",
          _PROFILE_FIELDS_SCHEMA),
    _tool("show_choice", "Ask the student to pick from cards. kind: countries, study_level, or intake.",
          {"kind": {"type": "string", "enum": list(CHOICE_QUESTIONS)}}, ["kind"]),
    _tool("show_budget_slider", "Ask the student for their yearly budget with a slider."),
    _tool("show_country_matches", "Show the countries that match the student's profile, ranked."),
    _tool("show_cost_calculator", "Show a live cost calculator (tuition + living) for ONE country.",
          {"country": {"type": "string", "description": "Country name or id"}}, ["country"]),
    _tool("show_country_facts", "Show quick facts for ONE country (costs, intakes, requirements, visa).",
          {"country": {"type": "string", "description": "Country name or id"}}, ["country"]),
    _tool("compare_countries", "Compare 2-3 countries side by side.",
          {"countries": {"type": "array", "items": {"type": "string"}, "description": "2-3 country names or ids"}},
          ["countries"]),
    _tool("check_eligibility", "Check the student's scores against ONE country's entry requirements.",
          {"country": {"type": "string", "description": "Country name or id"}}, ["country"]),
    _tool("show_profile", "Show the student what you know about them so far."),
    _tool("show_lead_form", "Show a short contact form so a counselor can follow up."),
]


@dataclass
class ToolOutcome:
    block: UIBlock | None
    message: str  # for the LLM only; never shown to the student verbatim
    changed: list[str] = field(default_factory=list)


def _no_block(reason: str) -> ToolOutcome:
    return ToolOutcome(None, f"Nothing was shown. {reason}")


def _shown(block: UIBlock, summary: str) -> ToolOutcome:
    return ToolOutcome(
        block,
        f"The student now sees a '{block.title}' card. {summary} Do NOT repeat the card's contents; "
        "write at most one short sentence leading into it or asking what to do next.",
    )


def _money(cur: str, lo: int | None, hi: int | None) -> str | None:
    if lo is None or hi is None:
        return None
    return format_money_range(lo, hi, cur)


def _resolve(catalog: Catalog, value: str) -> str | None:
    """Map a country name/alias/id from the LLM onto a catalog id."""
    if catalog.get(value):
        return value
    found = catalog.find_in_text(str(value))
    return found[0] if found else None


def _resolve_many(catalog: Catalog, values) -> list[str]:
    out: list[str] = []
    for v in values or []:
        cid = _resolve(catalog, v)
        if cid and cid not in out:
            out.append(cid)
    return out


# ---- result-block cache ----

def _cached(profile: dict, spec: IntentSpec, key: str, build: Callable[[], UIBlock | None]) -> UIBlock | None:
    """Same intent + same inputs -> the stored block, unchanged. Changed inputs -> rebuilt + note."""
    cache_key = f"{spec.intent}:{key}"
    shown = profile.setdefault("shown", {})
    h = profile_hash(profile, spec.input_fields)
    prior = shown.get(cache_key)
    if prior:
        # A block cached at an older UI version is upgraded if possible, otherwise treated as a miss and rebuilt.
        upgraded = upgrade_stored_block(prior["block"])
        prior = {**prior, "block": upgraded} if is_current(upgraded) else None

    if prior and prior["hash"] == h:
        return UIBlock.model_validate(prior["block"])

    block = build()
    if block is None:
        return None

    stored = block
    if prior:
        prior_block = UIBlock.model_validate(prior["block"])
        if prior_block.data == block.data:
            block = prior_block  # inputs moved but the answer didn't: nothing to announce
            stored = prior_block
        else:
            changed = [FIELD_LABELS[f].lower() for f in spec.input_fields
                       if prior["inputs"].get(f) != profile.get(f)]
            if changed:
                block = block.model_copy(update={"changed_because": f"Updated because your {', '.join(changed)} changed"})

    shown[cache_key] = {"hash": h, "inputs": snapshot(profile, spec.input_fields), "block": stored.model_dump()}
    return block


# ---- tool implementations ----

# Which profile field each guided question fills.
_CHOICE_FIELD = {"countries": "countries", "study_level": "study_level", "intake": "intake", "country_one": "focus_country"}


def _show_choice(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    kind = args.get("kind")
    spec = INTENTS["choice"]
    if kind not in CHOICE_QUESTIONS:
        return _no_block("Unknown question kind.")
    question, multi, subtitle = CHOICE_QUESTIONS[kind]

    if kind in ("countries", "country_one"):
        options = [{"id": c.id, "label": c.label, "icon": c.icon} for c in catalog.countries]
        current = (profile.get("countries") or []) if kind == "countries" else (
            [profile["focus_country"]] if profile.get("focus_country") else [])
    elif kind == "study_level":
        options = [{"id": i, "label": l} for i, l in STUDY_LEVELS]
        current = [profile["study_level"]] if profile.get("study_level") else []
    else:
        seen: list[str] = []
        for c in catalog.countries:
            seen.extend(i for i in c.intakes if i not in seen)
        options = [{"id": i, "label": i} for i in seen]
        current = [profile["intake"]] if profile.get("intake") else []

    if not options:
        return _no_block(f"No {kind} options are configured. Ask in plain text, or offer a counselor.")

    block = build_block(
        spec.block_type,
        {"field": _CHOICE_FIELD[kind], "multi": multi, "options": options, "selected": [s for s in current if any(o["id"] == s for o in options)]},
        title=spec.title.format(question=question), subtitle=subtitle,
        fallback_text=f"{question} Options: {', '.join(o['label'] for o in options)}.",
    )
    return _shown(block, f"They will pick: {question}")


def _show_welcome(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    spec = INTENTS["welcome"]
    tiles = [{"id": i, "icon": icon, "title": title, "description": desc}
             for i, icon, title, desc, needs_catalog in JOURNEY if catalog.countries or not needs_catalog]
    block = build_block(
        spec.block_type, {"tiles": tiles}, title=spec.title,
        fallback_text="I can help you: " + ", ".join(t["title"].lower() for t in tiles) + ".",
    )
    return _shown(block, "It is the welcome: greet the student warmly in one sentence and invite them to pick where to start.")


def _show_cost_calculator(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    spec = INTENTS["cost_calculator"]
    cid = _resolve(catalog, args.get("country", ""))
    country = catalog.get(cid) if cid else None
    if not country:
        return _no_block("That country isn't in the catalog. Offer a counselor.")

    step = 500
    parts = []
    for pid, label, lo, hi in (("tuition", "Tuition / year", country.tuition_min, country.tuition_max),
                               ("living", "Living / year", country.living_min, country.living_max)):
        if lo is None or hi is None:
            continue  # only parts we actually have figures for
        mid = round((lo + hi) / 2 / step) * step
        parts.append({"id": pid, "label": label, "min": lo, "max": hi, "step": step, "value": max(lo, min(hi, mid))})
    if not parts:
        return _no_block(f"No cost figures are on file for {country.label}. Say so and offer a counselor.")

    block = build_block(
        spec.block_type,
        {"country_id": country.id, "currency": catalog.currency, "parts": parts,
         "note": "Typical ranges: your total depends on the university and city."},
        title=spec.title.format(country=country.label),
        fallback_text=f"{country.label} yearly cost: " + ", ".join(
            f"{p['label'].lower()} {_money(catalog.currency, p['min'], p['max'])}" for p in parts) + ".",
    )
    return _shown(block, f"They can drag tuition and living costs for {country.label} and see the yearly total.")


def _show_budget_slider(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    spec = INTENTS["budget"]
    bounds = catalog.slider_bounds()
    if not bounds:
        return _no_block("No cost data is configured, so ask for their budget in plain text.")
    lo, hi = bounds
    step = catalog.budget_step
    value = profile.get("budget") or ((lo + hi) // 2 // step) * step
    value = max(lo, min(hi, value))
    block = build_block(
        spec.block_type,
        {"field": "budget", "min": lo, "max": hi, "step": step, "value": value, "unit": catalog.currency},
        title=spec.title, fallback_text="What is your budget per year (tuition + living)?",
    )
    return _shown(block, "They will set a yearly budget.")


def _show_country_matches(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    spec = INTENTS["recommend_country"]
    items = score_countries(profile, catalog)
    if not items:
        needed = [FIELD_LABELS[f].lower() for f in ("budget", "english_score", "academic_score") if not profile.get(f)]
        return _no_block("Can't rank countries yet; missing: " + (", ".join(needed) or "catalog data")
                         + ". Ask the student for ONE of these (budget first, using show_budget_slider).")

    def build():
        return build_block(
            spec.block_type, {"items": items}, title=spec.title,
            fallback_text="Best matches: " + ", ".join(f"{i['label']} {i['score']}%" for i in items) + ".",
        )

    block = _cached(profile, spec, "all", build)
    return _shown(block, "Top match: " + f"{items[0]['label']} ({items[0]['score']}%).")


def _facts_rows(c: CountryRecord, cur: str) -> list[dict]:
    rows = [
        ("Tuition / year", _money(cur, c.tuition_min, c.tuition_max)),
        ("Living / year", _money(cur, c.living_min, c.living_max)),
        ("Intakes", ", ".join(c.intakes) or None),
        ("English requirement", f"IELTS {c.ielts_min:g}" if c.ielts_min is not None else None),
        ("Academic requirement", f"{c.academic_min_percent:g}%" if c.academic_min_percent is not None else None),
        ("Work rights", c.work_rights),
        ("Post-study visa", c.post_study_visa),
        ("Proof of funds", c.funds_required),
    ]
    return [{"label": l, "value": v} for l, v in rows if v]


def _show_country_facts(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    spec = INTENTS["country_facts"]
    cid = _resolve(catalog, args.get("country", ""))
    country = catalog.get(cid) if cid else None
    if not country:
        return _no_block("That country isn't in the catalog. Say you don't have details on it and offer a counselor.")
    rows = _facts_rows(country, catalog.currency)
    if not rows:
        return _no_block(f"No facts are on file for {country.label}. Say so and offer a counselor.")

    def build():
        return build_block(
            spec.block_type, {"icon": country.icon, "heading": f"{country.label} quick facts", "rows": rows},
            title=spec.title.format(country=country.label),
            fallback_text=f"{country.label}: " + "; ".join(f"{r['label']} {r['value']}" for r in rows) + ".",
        )

    block = _cached(profile, spec, country.id, build)
    return _shown(block, f"Facts for {country.label}.")


def _compare_countries(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    spec = INTENTS["compare"]
    ids = _resolve_many(catalog, args.get("countries"))[:3]
    if len(ids) < 2:
        return _no_block("Need at least two catalog countries to compare. Ask which two.")
    countries = [catalog.get(i) for i in ids]
    cur = catalog.currency

    facts = [
        ("Tuition / year", lambda c: _money(cur, c.tuition_min, c.tuition_max)),
        ("Living / year", lambda c: _money(cur, c.living_min, c.living_max)),
        ("Intakes", lambda c: ", ".join(c.intakes) or None),
        ("English requirement", lambda c: f"IELTS {c.ielts_min:g}" if c.ielts_min is not None else None),
        ("Work rights", lambda c: c.work_rights),
        ("Post-study visa", lambda c: c.post_study_visa),
    ]  # fixed row order, so a comparison always reads the same way
    rows = []
    for label, get in facts:
        values = [get(c) for c in countries]
        if any(values):
            rows.append({"label": label, "values": [v or "—" for v in values]})
    if not rows:
        return _no_block("No comparable facts are on file for those countries. Offer a counselor.")

    def build():
        return build_block(
            spec.block_type,
            {"columns": [{"id": c.id, "label": c.label, "icon": c.icon} for c in countries], "rows": rows},
            title=spec.title.format(countries=" vs ".join(c.label for c in countries)),
            fallback_text="Comparison: " + " vs ".join(c.label for c in countries) + ". "
            + " ".join(f"{r['label']}: " + " | ".join(r["values"]) + "." for r in rows),
        )

    block = _cached(profile, spec, "|".join(ids), build)
    return _shown(block, "Side-by-side comparison.")


def _check_eligibility(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    spec = INTENTS["eligibility"]
    cid = _resolve(catalog, args.get("country", ""))
    country = catalog.get(cid) if cid else None
    if not country:
        return _no_block("That country isn't in the catalog. Offer a counselor.")
    result = check_eligibility(profile, country)
    if not result:
        return _no_block(f"Can't check {country.label} yet: need the student's English and/or academic score "
                         "(ask for one) or the catalog has no minimums for it.")

    def build():
        return build_block(
            spec.block_type, result, title=spec.title.format(country=country.label),
            fallback_text=f"{country.label}: {result['verdict']} ({result['score']}%).",
        )

    block = _cached(profile, spec, country.id, build)
    return _shown(block, f"Result: {result['verdict']}.")


def _show_profile(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    spec = INTENTS["profile"]
    rows = profile_rows(profile, catalog.labels(), catalog.currency)
    if not rows:
        return _no_block("You don't know anything about the student yet. Ask what they're looking for.")
    missing = [FIELD_LABELS[f].lower() for f in missing_slots(profile)]

    def build():
        return build_block(
            spec.block_type, {"rows": rows, "missing": missing}, title=spec.title,
            actions=[{"id": "edit", "label": "Update my details"}],
            fallback_text="What I know: " + "; ".join(f"{r['label']}: {r['value']}" for r in rows) + ".",
        )

    block = _cached(profile, spec, "all", build)
    return _shown(block, "A summary of their profile.")


def _show_lead_form(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    spec = INTENTS["lead_form"]
    contact = profile.get("contact") or {}
    block = build_block(
        spec.block_type,
        {"fields": [
            {"id": "name", "label": "Full name", "type": "text", "required": True, "value": contact.get("name")},
            {"id": "email", "label": "Email", "type": "email", "required": True, "value": contact.get("email")},
            {"id": "phone", "label": "Phone", "type": "tel", "required": True, "value": contact.get("phone")},
        ]},
        title=spec.title, subtitle="A counselor will follow up with you",
        fallback_text="Please share your name, email and phone so a counselor can contact you.",
    )
    return _shown(block, "They will enter their contact details. Do NOT promise a callback or that anyone will contact them.")


def _update_profile(args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    updates = dict(args)
    if "countries" in updates:
        updates["countries"] = _resolve_many(catalog, updates["countries"])
    changed = apply_updates(profile, updates)
    if not changed:
        return ToolOutcome(None, "Profile unchanged (nothing new or unrecognized values).")
    return ToolOutcome(None, "Saved: " + ", ".join(FIELD_LABELS[f].lower() for f in changed)
                       + ". Continue helping; show a card if it answers their question.", changed)


_EXECUTORS: dict[str, Callable[[dict, dict, Catalog], ToolOutcome]] = {
    "update_profile": _update_profile,
    "show_choice": _show_choice,
    "show_budget_slider": _show_budget_slider,
    "show_country_matches": _show_country_matches,
    "show_welcome": _show_welcome,
    "show_cost_calculator": _show_cost_calculator,
    "show_country_facts": _show_country_facts,
    "compare_countries": _compare_countries,
    "check_eligibility": _check_eligibility,
    "show_profile": _show_profile,
    "show_lead_form": _show_lead_form,
}


def execute_education_tool(name: str, args: dict, profile: dict, catalog: Catalog) -> ToolOutcome:
    fn = _EXECUTORS.get(name)
    if fn is None:
        return _no_block(f"Unknown tool {name}.")
    try:
        return fn(args or {}, profile, catalog)
    except BlockValidationError as e:
        # An invalid block must never reach the widget; degrade to text.
        logger.error("[EDU] %s produced an invalid block: %s", name, e)
        return _no_block("The card could not be built. Answer in plain text.")


def tool_for_intent(intent: str) -> str:
    return INTENTS[intent].tool


assert set(TOOL_TO_INTENT) <= set(_EXECUTORS), "every registry tool needs an executor"
