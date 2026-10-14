"""Backend block types and the widget's renderer registry are maintained by hand in separate places.
These tests read the widget source as text (no Node needed) and fail loudly if the two drift apart."""
import re
from pathlib import Path

from app.schemas.ui_blocks import DATA_MODELS

BLOCKS_DIR = Path(__file__).resolve().parents[2] / "widget" / "src" / "components" / "blocks"


def _keys_of(source: str, anchor: str, closer: str) -> set[str]:
    """Identifiers between `anchor` and the first `closer` after it."""
    start = source.index(anchor) + len(anchor)
    body = source[start:source.index(closer, start)]
    return set(re.findall(r"^\s*([a-z_]+)\s*:", body, re.M)) or set(re.findall(r"'([a-z_]+)'", body))


def _renderer_types() -> set[str]:
    return _keys_of((BLOCKS_DIR / "BlockRenderer.tsx").read_text(), "const REGISTRY: Record<string, ComponentType<BlockComponentProps>> = {", "\n}")


def _collapsible_types() -> set[str]:
    src = (BLOCKS_DIR / "AnswerSummary.tsx").read_text()
    return set(re.findall(r"'([a-z_]+)'", src[src.index("COLLAPSIBLE = new Set(["):].split("])")[0]))


def test_every_backend_block_type_has_a_widget_component():
    missing = set(DATA_MODELS) - _renderer_types()
    assert not missing, f"backend can emit block types the widget cannot render: {sorted(missing)}"


def test_widget_has_no_component_for_a_type_the_backend_cannot_emit():
    extra = _renderer_types() - set(DATA_MODELS)
    assert not extra, f"widget renders types missing from the backend schema: {sorted(extra)}"


def test_collapsible_types_are_real_block_types():
    assert _collapsible_types(), "could not read COLLAPSIBLE from AnswerSummary.tsx (format changed?)"
    assert _collapsible_types() <= set(DATA_MODELS)


# ---- UI registry (UI_TYPES) <-> widget ----

from app.schemas.ui_blocks import UI_TYPES  # noqa: E402


def _dim_when_locked_types() -> set[str]:
    src = (BLOCKS_DIR / "BlockRenderer.tsx").read_text()
    return set(re.findall(r"'([a-z_]+)'", src[src.index("DIM_WHEN_LOCKED = new Set(["):].split("])")[0]))


def test_registry_and_derived_schema_map_agree():
    assert set(UI_TYPES) == set(DATA_MODELS)
    assert all(DATA_MODELS[t] is s.data_model for t, s in UI_TYPES.items())


def test_registry_types_equal_widget_renderer_types():
    assert set(UI_TYPES) == _renderer_types()


def test_registry_collapsible_flags_equal_widget_collapsible_set():
    assert {t for t, s in UI_TYPES.items() if s.collapsible} == _collapsible_types()


def test_registry_dim_flags_equal_widget_dim_when_locked_set():
    assert _dim_when_locked_types(), "could not read DIM_WHEN_LOCKED from BlockRenderer.tsx (format changed?)"
    assert {t for t, s in UI_TYPES.items() if s.dims_when_locked} == _dim_when_locked_types()


def test_every_registered_type_is_documented_and_versioned():
    for t, s in UI_TYPES.items():
        assert s.type == t
        assert s.description.strip() and s.when_to_use.strip(), t
        assert s.version >= 1, t


def test_built_blocks_carry_the_registry_version():
    from app.schemas.ui_blocks import build_block
    block = build_block("quick_chips", {"chips": [{"id": "a", "label": "A"}]}, fallback_text="A")
    assert block.schema_version == UI_TYPES["quick_chips"].version


# ---- widget SUPPORTED_VERSIONS <-> backend versions ----

def _widget_supported_versions() -> dict[str, list[int]]:
    src = (BLOCKS_DIR / "blockVersions.ts").read_text()
    body = src[src.index("SUPPORTED_VERSIONS: Record<string, number[]> = {"):]
    body = body[:body.index("\n}")]
    return {m[1]: [int(v) for v in re.findall(r"\d+", m[2])]
            for m in re.finditer(r"^\s*([a-z_]+):\s*\[([\d,\s]*)\]", body, re.M)}


def test_widget_version_table_covers_exactly_the_registered_types():
    assert set(_widget_supported_versions()) == set(UI_TYPES)


def test_widget_can_render_the_version_the_backend_emits_for_every_type():
    # Fails when a backend `version` is bumped before the widget lists it (rollout rule: widget first, backend second).
    supported = _widget_supported_versions()
    behind = {t: (s.version, supported[t]) for t, s in UI_TYPES.items() if s.version not in supported[t]}
    assert not behind, f"widget cannot render the backend's current version: {behind}"


def test_widget_version_lists_are_well_formed():
    for t, versions in _widget_supported_versions().items():
        assert versions and all(v >= 1 for v in versions) and versions == sorted(set(versions)), t
