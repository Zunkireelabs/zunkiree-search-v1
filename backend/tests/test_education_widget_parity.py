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
