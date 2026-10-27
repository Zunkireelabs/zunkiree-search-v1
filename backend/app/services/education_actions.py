"""
Validation of a tapped UI action (`block_action`) before the agent trusts it.

The widget sends {blockId, blockType, actionId, values}. Without a check, anyone can post any block id, any action and
any values. A tap is accepted only if it points at a real block shown in THIS session and asks for something that block
offered: an action the registry allows for its type (or the block lists itself, or a quick-chip id), with values that fit
the block's own data (its field, its options, its slider range). `validate_block_action` returns None when the tap is
fine, otherwise a short reason code. A rejected tap is dropped by the caller and the turn continues as plain typed text.
"""
from typing import Any

from app.schemas.ui_blocks import UI_TYPES

# How many recent messages to search for the block (matches what the widget restores after a reload).
BLOCK_LOOKUP_WINDOW = 50


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value  # excludes bool and NaN


def _check_select(block_type: str, data: dict, values: dict) -> str | None:
    if values.get("field") != data.get("field"):
        return "wrong_field"
    selected = values.get("selected")
    if not isinstance(selected, list) or not all(isinstance(s, str) for s in selected):
        return "bad_values"
    if not set(selected) <= {o.get("id") for o in data.get("options") or []}:
        return "not_an_option"
    if not data.get("multi") and len(selected) > 1:
        return "too_many_selected"
    return None


def _check_set_value(block_type: str, data: dict, values: dict) -> str | None:
    value = values.get("value")
    if not _is_number(value):
        return "bad_values"
    if block_type == "range_slider":
        if values.get("field") != data.get("field"):
            return "wrong_field"
        low, high = data.get("min"), data.get("max")
    else:  # cost_calculator: the total of its parts becomes the budget
        if values.get("field") != "budget":
            return "wrong_field"
        parts = data.get("parts") or []
        low, high = sum(p.get("min", 0) for p in parts), sum(p.get("max", 0) for p in parts)
    if not (_is_number(low) and _is_number(high) and low <= value <= high):
        return "out_of_range"
    return None


def _check_start(block_type: str, data: dict, values: dict) -> str | None:
    return None if values.get("journey") in {t.get("id") for t in data.get("tiles") or []} else "not_an_option"


def _check_explore(block_type: str, data: dict, values: dict) -> str | None:
    return None if values.get("country") in {i.get("id") for i in data.get("items") or []} else "not_an_option"


def _check_open_university(block_type: str, data: dict, values: dict) -> str | None:
    return None if values.get("university_id") in {i.get("university_id") for i in data.get("items") or []} else "not_an_option"


def _check_submit(block_type: str, data: dict, values: dict) -> str | None:
    if not all(isinstance(v, str) for v in values.values()):
        return "bad_values"
    return None if set(values) <= {f.get("id") for f in data.get("fields") or []} else "wrong_field"


_VALUE_CHECKS = {
    "select": _check_select,
    "set_value": _check_set_value,
    "start": _check_start,
    "explore": _check_explore,
    "open_university": _check_open_university,
    "submit": _check_submit,
}


def validate_block_action(action: Any, block: dict | None) -> str | None:
    """None if the tap is acceptable, else a reason code. `block` is the stored block the tap claims to come from."""
    if not isinstance(action, dict):
        return "malformed"
    block_id, block_type, action_id = action.get("blockId"), action.get("blockType"), action.get("actionId")
    values = action.get("values", {})
    if not all(isinstance(x, str) and x for x in (block_id, block_type, action_id)) or not isinstance(values, dict):
        return "malformed"
    if block is None:
        return "unknown_block"
    if block.get("type") != block_type:
        return "type_mismatch"
    spec = UI_TYPES.get(block_type)
    if spec is None:
        return "unknown_type"

    data = block.get("data") or {}
    offered = set(spec.allowed_actions) | {a.get("id") for a in block.get("actions") or []}
    if block_type == "quick_chips":
        offered |= {c.get("id") for c in data.get("chips") or []}   # chip ids are data-defined
    if action_id not in offered:
        return "action_not_offered"

    check = _VALUE_CHECKS.get(action_id)
    return check(block_type, data, values) if check else None
