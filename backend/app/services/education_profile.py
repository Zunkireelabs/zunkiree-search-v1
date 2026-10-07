"""
Student profile for the education agent: what we know about the visitor.

Updated two ways, both through the same whitelist so the profile can't be
polluted with arbitrary keys:
  - a tap on a UI block (structured action, applied by `apply_block_action`,
    no LLM parsing), or
  - the `update_profile` tool, when the student states something in free text.

`profile["shown"]` remembers which blocks were shown and for which inputs, so the
same question with an unchanged profile re-shows the identical block.
"""
import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger("zunkiree.education_profile")

# field -> kind. Anything not listed here is rejected.
FIELDS: dict[str, str] = {
    "countries": "list",
    "study_level": "str",
    "field_of_study": "str",
    "intake": "str",
    "english_test": "str",
    "budget": "num",
    "english_score": "num",
    "academic_score": "num",
    "focus_country": "str",
}

FIELD_LABELS: dict[str, str] = {
    "countries": "Countries",
    "study_level": "Study level",
    "field_of_study": "Field of study",
    "budget": "Budget",
    "intake": "Intake",
    "english_test": "English test",
    "english_score": "English score",
    "academic_score": "Academic score",
    "focus_country": "Looking at",
}

# Order of the "what to ask next" checklist.
# Slots that have a card (countries, level, budget, intake) come first so the guided flow can
# run deterministically; the text-only ones (subject, English score) are asked last.
SLOT_ORDER = ["countries", "study_level", "budget", "intake", "field_of_study", "english_score"]

CONTACT_FIELDS = ("name", "email", "phone")


def new_profile() -> dict:
    return {"contact": {}, "shown": {}}


def _coerce(kind: str, value: Any) -> Any:
    """Return the cleaned value, or None if it isn't usable."""
    if kind == "list":
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return None
        out = [str(v).strip() for v in value if str(v).strip()]
        return sorted(set(out)) or None
    if kind == "str":
        s = str(value).strip() if value is not None else ""
        return s[:100] or None
    if kind == "num":
        try:
            n = float(value)
        except (TypeError, ValueError):
            return None
        return int(n) if n.is_integer() else n
    return None


def set_field(profile: dict, field: str, value: Any) -> bool:
    """Set one whitelisted field. Returns True only if the stored value changed."""
    kind = FIELDS.get(field)
    if kind is None:
        return False
    clean = _coerce(kind, value)
    if clean is None or profile.get(field) == clean:
        return False
    profile[field] = clean
    return True


def apply_updates(profile: dict, updates: dict) -> list[str]:
    """Apply free-text-extracted updates (update_profile tool). Returns changed field names."""
    return [f for f, v in (updates or {}).items() if set_field(profile, f, v)]


def apply_block_action(profile: dict, action: dict | None) -> list[str]:
    """Apply a structured tap from a UI block. Returns changed field names."""
    if not action:
        return []
    action_id = action.get("actionId")
    values = action.get("values") or {}
    changed: list[str] = []

    if action_id == "select":
        field = values.get("field")
        selected = values.get("selected") or []
        if field == "countries":
            if set_field(profile, "countries", selected):
                changed.append("countries")
        elif field in FIELDS and selected:
            if set_field(profile, field, selected[0]):
                changed.append(field)
    elif action_id == "set_value":
        field = values.get("field")
        if field in FIELDS and set_field(profile, field, values.get("value")):
            changed.append(field)
    elif action_id == "explore":
        if set_field(profile, "focus_country", values.get("country")):
            changed.append("focus_country")
    elif action_id == "submit":
        contact = {k: str(values.get(k, "")).strip()[:200] for k in CONTACT_FIELDS if values.get(k)}
        if contact and contact != profile.get("contact"):
            profile["contact"] = contact
            changed.append("contact")
    return changed


def profile_hash(profile: dict, fields: tuple[str, ...]) -> str:
    """Hash of only the fields that matter to one block, so unrelated updates don't invalidate it."""
    snapshot = {f: profile.get(f) for f in fields}
    return hashlib.sha1(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:12]


def snapshot(profile: dict, fields: tuple[str, ...]) -> dict:
    return {f: profile.get(f) for f in fields}


def missing_slots(profile: dict) -> list[str]:
    return [f for f in SLOT_ORDER if not profile.get(f)]


def display_value(field: str, value: Any, currency: str = "$") -> str:
    if isinstance(value, list):
        return ", ".join(value)
    if field == "budget":
        return f"{currency}{int(value):,} / year"
    return str(value)


def profile_rows(profile: dict, labels: dict[str, str] | None = None, currency: str = "$") -> list[dict]:
    """Rows for the profile_summary block. `labels` maps ids (e.g. 'uk') to display names."""
    labels = labels or {}
    rows = []
    for field in FIELD_LABELS:
        value = profile.get(field)
        if not value:
            continue
        if field in ("countries", "focus_country"):
            value = [labels.get(v, v) for v in value] if isinstance(value, list) else labels.get(value, value)
        rows.append({"label": FIELD_LABELS[field], "value": display_value(field, value, currency)})
    return rows


def progress(profile: dict) -> dict:
    """How much of the guided profile is filled: drives the widget's slim progress bar."""
    return {"filled": sum(1 for f in SLOT_ORDER if profile.get(f)), "total": len(SLOT_ORDER)}


def has_any_data(profile: dict) -> bool:
    return any(profile.get(f) for f in FIELDS) or bool(profile.get("contact"))


def merge_profiles(base: dict, other: dict) -> list[str]:
    """Fill gaps in `base` from `other` (e.g. the same student's profile from another device). Returns filled fields."""
    filled = [f for f in FIELDS if not base.get(f) and other.get(f) and set_field(base, f, other[f])]
    if other.get("contact") and not base.get("contact"):
        base["contact"] = dict(other["contact"])
        filled.append("contact")
    return filled
