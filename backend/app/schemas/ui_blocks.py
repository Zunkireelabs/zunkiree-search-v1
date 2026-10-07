"""
Generative-UI block schema.

The agent picks a block TYPE; deterministic code builds `data` from real tenant
data and validates it here. The LLM never writes block JSON. The widget owns the
look (one component per type), so the same type always renders the same way.

Every block carries `fallback_text` so channels that can't render UI (voice,
Instagram, Orca adapters) get a clean text version.
"""
import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

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


class MatchItem(BaseModel):
    id: str
    label: str
    icon: str | None = None
    score: int = Field(ge=0, le=100)
    reasons: list[str] = []


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
    score: int = Field(ge=0, le=100)
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


DATA_MODELS: dict[str, type[BaseModel]] = {
    "stepper": StepperData,
    "accordion": AccordionData,
    "checklist": ChecklistData,
    "timeline": TimelineData,
    "cost_calculator": CostCalculatorData,
    "journey_cards": JourneyCardsData,
    "choice_cards": ChoiceCardsData,
    "quick_chips": QuickChipsData,
    "range_slider": RangeSliderData,
    "match_cards": MatchCardsData,
    "info_card": InfoCardData,
    "comparison_table": ComparisonData,
    "eligibility_meter": EligibilityData,
    "profile_summary": ProfileSummaryData,
    "lead_form": LeadFormData,
}


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
