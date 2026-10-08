"""
Generative-UI block schema.

The agent picks a block TYPE; deterministic code builds `data` from real tenant
data and validates it here. The LLM never writes block JSON. The widget owns the
look (one component per type), so the same type always renders the same way.

Every block carries `fallback_text` so channels that can't render UI (voice,
Instagram, Orca adapters) get a clean text version.
"""
import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

SCHEMA_VERSION = 1


class BlockValidationError(ValueError):
    """Raised when a block's data doesn't match its type's schema."""


# ---- per-type data shapes (mirrored by widget/src/components/blocks/types.ts) ----

class ChoiceOption(BaseModel):
    id: str
    label: str
    icon: str | None = None
    hint: str | None = None


class ChoiceCardsData(BaseModel):
    field: str
    multi: bool
    options: list[ChoiceOption] = Field(min_length=1)
    selected: list[str] = []


class Chip(BaseModel):
    id: str
    label: str


class QuickChipsData(BaseModel):
    chips: list[Chip] = Field(min_length=1)


class RangeSliderData(BaseModel):
    field: str
    min: float
    max: float
    step: float = Field(gt=0)
    value: float
    unit: str

    @model_validator(mode="after")
    def _bounds(self):
        if not self.min < self.max:
            raise ValueError("min must be < max")
        if not self.min <= self.value <= self.max:
            raise ValueError("value must be within [min, max]")
        return self


class MatchReason(BaseModel):
    text: str
    status: Literal["pass", "partial", "fail", "info"]


class MatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")   # a v1-shaped item (with a percentage score) must not slip through
    id: str
    label: str
    icon: str | None = None
    tier: Literal["strong", "good", "possible", "needs_review"]
    tier_label: str
    reasons: list[MatchReason] = []


class MatchCardsData(BaseModel):
    items: list[MatchItem] = Field(min_length=1)


class InfoRow(BaseModel):
    label: str
    value: str


class InfoCardData(BaseModel):
    icon: str | None = None
    heading: str
    rows: list[InfoRow] = Field(min_length=1)


class ComparisonColumn(BaseModel):
    id: str
    label: str
    icon: str | None = None


class ComparisonRow(BaseModel):
    label: str
    values: list[str]


class ComparisonData(BaseModel):
    columns: list[ComparisonColumn] = Field(min_length=2)
    rows: list[ComparisonRow] = Field(min_length=1)

    @model_validator(mode="after")
    def _row_width(self):
        for row in self.rows:
            if len(row.values) != len(self.columns):
                raise ValueError(f"row '{row.label}' has {len(row.values)} values for {len(self.columns)} columns")
        return self


class EligibilityCheck(BaseModel):
    label: str
    ok: bool
    detail: str


class EligibilityData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: str
    checks: list[EligibilityCheck] = Field(min_length=1)


class ProfileSummaryData(BaseModel):
    welcome_back: bool = False
    rows: list[InfoRow] = Field(min_length=1)
    missing: list[str] = []


class LeadField(BaseModel):
    id: str
    label: str
    type: str = Field(pattern="^(text|email|tel)$")
    required: bool = False
    value: str | None = None


class LeadFormData(BaseModel):
    fields: list[LeadField] = Field(min_length=1)


class StepperStep(BaseModel):
    title: str
    detail: str | None = None


class StepperData(BaseModel):
    steps: list[StepperStep] = Field(min_length=2)


class AccordionItem(BaseModel):
    title: str
    summary: str | None = None
    detail: str


class AccordionData(BaseModel):
    items: list[AccordionItem] = Field(min_length=1)


class ChecklistItem(BaseModel):
    label: str
    note: str | None = None


class ChecklistData(BaseModel):
    items: list[ChecklistItem] = Field(min_length=1)


class TimelineEvent(BaseModel):
    when: str
    title: str
    detail: str | None = None


class TimelineData(BaseModel):
    events: list[TimelineEvent] = Field(min_length=2)


class CostPart(BaseModel):
    id: str
    label: str
    min: float
    max: float
    step: float = Field(gt=0)
    value: float

    @model_validator(mode="after")
    def _bounds(self):
        if not self.min <= self.value <= self.max:
            raise ValueError(f"cost part '{self.id}': value must be within [min, max]")
        return self


class CostCalculatorData(BaseModel):
    country_id: str | None = None
    currency: str
    parts: list[CostPart] = Field(min_length=1)
    note: str | None = None


class JourneyTile(BaseModel):
    id: str
    icon: str | None = None
    title: str
    description: str


class JourneyCardsData(BaseModel):
    tiles: list[JourneyTile] = Field(min_length=2)


@dataclass(frozen=True)
class UISpec:
    """One registered UI type: the single place that says what it is and how it behaves.

    `collapsible` / `dims_when_locked` mirror the widget's COLLAPSIBLE / DIM_WHEN_LOCKED sets and
    `allowed_actions` records the action ids the widget emits; tests keep the widget in sync.
    `allowed_actions` is declarative for now (not enforced yet)."""
    type: str
    description: str
    when_to_use: str
    data_model: type[BaseModel]
    version: int = 1
    allowed_actions: tuple[str, ...] = ()
    collapsible: bool = False        # input block that folds into a one-line answer once answered
    dims_when_locked: bool = False   # looks "used up" once superseded or answered
    # from-version -> function turning that version's `data` into the next version's. Needed when `version` is bumped so
    # blocks stored at an older version (history, caches) still render; see upgrade_stored_block.
    upgraders: dict[int, Callable[[dict], dict]] = field(default_factory=dict)


UI_TYPES: dict[str, UISpec] = {s.type: s for s in [
    UISpec("choice_cards", "Pick one or more options from cards.", "Collect a profile answer such as countries, study level or intake.",
           ChoiceCardsData, allowed_actions=("select",), collapsible=True, dims_when_locked=True),
    UISpec("range_slider", "Pick a number on a slider.", "Collect a numeric answer such as a yearly budget.",
           RangeSliderData, allowed_actions=("set_value",), collapsible=True, dims_when_locked=True),
    UISpec("journey_cards", "Welcome tiles that start a guided journey.", "Open the conversation or offer the next step.",
           JourneyCardsData, allowed_actions=("start",), collapsible=True, dims_when_locked=True),
    UISpec("lead_form", "Short contact form.", "Let the student ask for a counselor.",
           LeadFormData, allowed_actions=("submit",), collapsible=True, dims_when_locked=True),
    UISpec("quick_chips", "Row of tappable suggestion chips.", "Offer quick follow-up topics. Chip ids are data-defined, so no fixed actions. No backend tool emits it yet.",
           QuickChipsData, dims_when_locked=True),
    UISpec("match_cards", "Destinations grouped by how well they fit what the student told us, each with its reasons.",
           "Answer which countries fit the student's profile. A fit tier is not a chance of admission or of a visa.",
           MatchCardsData, version=2, allowed_actions=("explore",), dims_when_locked=True),
    UISpec("profile_summary", "What we know about the student.", "Show or confirm the saved profile.",
           ProfileSummaryData, allowed_actions=("edit",), dims_when_locked=True),
    UISpec("info_card", "Heading with label/value rows.", "Quick facts about one country.", InfoCardData),
    UISpec("comparison_table", "Side-by-side table of 2-3 columns.", "Compare countries.", ComparisonData),
    UISpec("eligibility_meter", "Pass/fail checks against entry requirements.", "Check the student's scores against one country.",
           EligibilityData, version=2),
    UISpec("cost_calculator", "Adjustable cost parts with a live total.", "Estimate yearly cost for one country.",
           CostCalculatorData, allowed_actions=("set_value",)),
    UISpec("stepper", "Ordered steps.", "A process taken from the knowledge base.", StepperData),
    UISpec("checklist", "Things to prepare.", "Documents or requirements taken from the knowledge base.", ChecklistData),
    UISpec("timeline", "Dated events.", "Dates and deadlines taken from the knowledge base.", TimelineData),
    UISpec("accordion", "Expandable items with a summary.", "Services or options taken from the knowledge base.", AccordionData),
]}

# Derived view kept for existing callers: type -> data model.
DATA_MODELS: dict[str, type[BaseModel]] = {t: s.data_model for t, s in UI_TYPES.items()}


def _version_of(block: dict) -> int | None:
    version = block.get("schema_version", 1)   # blocks stored before versions existed are v1
    return version if isinstance(version, int) and not isinstance(version, bool) else None


def _spec_of(block: dict) -> UISpec | None:
    block_type = block.get("type")
    return UI_TYPES.get(block_type) if isinstance(block_type, str) else None


def is_current(block: dict) -> bool:
    """True when a stored block is a registered type at the registry's current version."""
    spec = _spec_of(block)
    return spec is not None and _version_of(block) == spec.version


def upgrade_stored_block(block: dict) -> dict:
    """A block stored at an older version, brought up to the current version through the registry's upgraders.

    Returns the block unchanged when it is already current, of an unknown type, NEWER than this backend, or cannot be
    upgraded (a step is missing, an upgrader raises, or the result fails the current schema). The caller then rebuilds
    it or the widget shows its `fallback_text`. Never mutates its input; keeps `block_id` so taps still resolve."""
    spec, version = _spec_of(block), _version_of(block)
    if spec is None or version is None or version >= spec.version:
        return block
    data = copy.deepcopy(block.get("data") or {})
    try:
        for from_version in range(version, spec.version):
            step = spec.upgraders.get(from_version)
            if step is None:
                return block
            data = step(data)
        clean = spec.data_model.model_validate(data).model_dump(exclude_none=True)
    except Exception:
        return block
    return {**block, "data": clean, "schema_version": spec.version}


class BlockAction(BaseModel):
    id: str
    label: str


class UIBlock(BaseModel):
    block_id: str
    type: str
    schema_version: int = SCHEMA_VERSION
    title: str | None = None
    subtitle: str | None = None
    data: dict[str, Any]
    actions: list[BlockAction] = []
    fallback_text: str
    # Set when the same block is re-shown with new content because the profile changed.
    changed_because: str | None = None
    # Knowledge-base pages the content came from (blocks built from KB text only).
    sources: list[str] = []
    # What the student submitted on this block (set after they act); the widget collapses it to a summary.
    answered: dict | None = None

    @model_validator(mode="after")
    def _known_type(self):
        if self.type not in DATA_MODELS:
            raise ValueError(f"unknown block type '{self.type}'")
        return self


def _block_id(block_type: str, data: dict) -> str:
    # Deterministic: identical content always gets the identical id.
    digest = hashlib.sha1(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:10]
    return f"{block_type}-{digest}"


def build_block(
    block_type: str,
    data: dict,
    *,
    fallback_text: str,
    title: str | None = None,
    subtitle: str | None = None,
    actions: list[dict] | None = None,
    changed_because: str | None = None,
    sources: list[str] | None = None,
) -> UIBlock:
    """Validate `data` against the type's schema and return the block, or raise BlockValidationError."""
    model = DATA_MODELS.get(block_type)
    if model is None:
        raise BlockValidationError(f"unknown block type '{block_type}'")
    try:
        clean = model.model_validate(data).model_dump(exclude_none=True)
        return UIBlock(
            block_id=_block_id(block_type, clean),
            type=block_type,
            schema_version=UI_TYPES[block_type].version,
            title=title,
            subtitle=subtitle,
            data=clean,
            actions=[BlockAction(**a) for a in (actions or [])],
            fallback_text=fallback_text,
            changed_because=changed_because,
            sources=sources or [],
        )
    except ValidationError as e:
        raise BlockValidationError(str(e)) from e
