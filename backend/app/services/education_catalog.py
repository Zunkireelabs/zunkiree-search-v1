"""
Per-tenant education catalog: the structured facts behind the UI blocks
(destination countries, cost ranges, intakes, entry requirements).

Rule: nothing here is invented. Every field is optional, and the block builders
only show a row when the tenant supplied that fact. No data -> no card; the
agent says it doesn't have that detail and offers a counselor instead.

Source today: a JSON file per site at app/data/education_catalogs/<site_id>.json
(imported from the tenant's own data). A DB-backed loader replaces this later
behind the same `get_catalog()` call. All money values are in one currency per
catalog (`currency` is its ISO code; a legacy symbol such as "$" is normalised to "USD" on load).
"""
import json
import logging
import re
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.services.money import format_money, normalize_currency

logger = logging.getLogger("zunkiree.education_catalog")

CATALOG_DIR = Path(__file__).resolve().parent.parent / "data" / "education_catalogs"

# Fit tiers, from what the student told us and what the catalog states. No weights and no percentages.
TIER_ORDER = ("strong", "good", "possible", "needs_review")
TIER_LABELS = {"strong": "Strong fit", "good": "Good fit", "possible": "Possible fit", "needs_review": "Needs review"}


class CountryRecord(BaseModel):
    id: str
    label: str
    aliases: list[str] = []
    icon: str | None = None
    tuition_min: int | None = None
    tuition_max: int | None = None
    living_min: int | None = None
    living_max: int | None = None
    intakes: list[str] = []
    ielts_min: float | None = None
    academic_min_percent: float | None = None
    work_rights: str | None = None
    post_study_visa: str | None = None
    funds_required: str | None = None
    visa_notes: str | None = None

    @property
    def yearly_min(self) -> int | None:
        if self.tuition_min is None or self.living_min is None:
            return None
        return self.tuition_min + self.living_min

    @property
    def yearly_max(self) -> int | None:
        if self.tuition_max is None or self.living_max is None:
            return None
        return self.tuition_max + self.living_max


class Catalog(BaseModel):
    site_id: str
    currency: str = "USD"
    status: str = "verified"
    countries: list[CountryRecord] = Field(default_factory=list)
    # Budget slider bounds. Optional: derived from country costs when absent.
    budget_min: int | None = None
    budget_max: int | None = None
    budget_step: int = 1000

    @field_validator("currency", mode="before")
    @classmethod
    def _iso_currency(cls, value):
        return normalize_currency(value) if isinstance(value, str) else value

    def get(self, country_id: str) -> CountryRecord | None:
        return next((c for c in self.countries if c.id == country_id), None)

    def labels(self) -> dict[str, str]:
        return {c.id: c.label for c in self.countries}

    def find_in_text(self, text: str) -> list[str]:
        """Country ids mentioned in `text` (by label or alias), in catalog order."""
        lowered = text.lower()
        found = []
        for c in self.countries:
            names = {c.label, c.id, *c.aliases}
            if any(re.search(rf"(?<!\w){re.escape(n.lower())}(?!\w)", lowered) for n in names):
                found.append(c.id)
        return found

    def slider_bounds(self) -> tuple[int, int] | None:
        if self.budget_min is not None and self.budget_max is not None:
            return self.budget_min, self.budget_max
        mins = [c.yearly_min for c in self.countries if c.yearly_min is not None]
        maxs = [c.yearly_max for c in self.countries if c.yearly_max is not None]
        if not mins or not maxs:
            return None
        step = self.budget_step
        return (min(mins) // step) * step, -(-max(maxs) // step) * step


_EMPTY: dict[str, Catalog] = {}
_registry: dict[str, Catalog] = {}


def register_catalog(catalog: Catalog) -> None:
    _registry[catalog.site_id] = catalog


def load_catalog_file(path: Path) -> Catalog | None:
    try:
        catalog = Catalog.model_validate(json.loads(path.read_text()))
    except (OSError, ValueError, ValidationError) as e:
        logger.error("education catalog %s is invalid: %s", path.name, e)
        return None
    if catalog.status != "verified":
        logger.warning("education catalog %s has status=%s (not verified by the tenant)", path.name, catalog.status)
    return catalog


def get_catalog(site_id: str) -> Catalog:
    """The tenant's catalog, or an empty one (agent then answers from the knowledge base only)."""
    if site_id in _registry:
        return _registry[site_id]
    path = CATALOG_DIR / f"{site_id}.json"
    if path.is_file():
        catalog = load_catalog_file(path)
        if catalog:
            _registry[site_id] = catalog
            return catalog
    return _EMPTY.setdefault(site_id, Catalog(site_id=site_id))


def _fmt(currency: str, n: int) -> str:
    return format_money(n, currency)


def _tier(passed: int, partial: int, failed: int) -> str:
    """The tier is a statement about which of the student's own details line up with the catalog's. It is NOT a chance of
    admission or of a visa. Any failed check -> needs review; otherwise two or more checks that all pass -> strong; at most
    one partial -> good; more -> possible."""
    if failed:
        return "needs_review"
    if not partial and passed >= 2:
        return "strong"
    if partial <= 1:
        return "good"
    return "possible"


def fit_countries(profile: dict, catalog: Catalog) -> list[dict]:
    """
    Deterministic country fit. Pure function of (profile, catalog): the same inputs always give the same items in the
    same order (tier, then more passed checks, then id). Each check is pass / partial / fail, or skipped when the profile
    or the catalog doesn't have the data, so missing data never fakes a result. A country with no budget, English or
    academic check to run is left out (an intake alone is not enough to say anything).
    """
    cur = catalog.currency
    budget = profile.get("budget")
    english = profile.get("english_score")
    academic = profile.get("academic_score")
    intake = profile.get("intake") or ""
    items = []

    for c in catalog.countries:
        reasons: list[dict] = []
        hard = 0  # budget / English / academic checks that could be run

        if budget is not None and c.yearly_min is not None and c.yearly_max is not None:
            hard += 1
            if budget >= c.yearly_max:
                reasons.append({"status": "pass", "text": f"Fits your {_fmt(cur, budget)} budget"})
            elif budget >= c.yearly_min:
                reasons.append({"status": "partial", "text":
                                f"Within your budget for most options ({_fmt(cur, c.yearly_min)}–{_fmt(cur, c.yearly_max)}/yr)"})
            else:
                reasons.append({"status": "fail", "text": f"Above your budget (from {_fmt(cur, c.yearly_min)}/yr)"})

        if english is not None and c.ielts_min is not None:
            hard += 1
            ok = english >= c.ielts_min
            reasons.append({"status": "pass" if ok else "fail", "text":
                            f"English score {'meets' if ok else 'is below'} the {c.ielts_min:g} minimum"})

        if academic is not None and c.academic_min_percent is not None:
            hard += 1
            ok = academic >= c.academic_min_percent
            reasons.append({"status": "pass" if ok else "fail", "text":
                            f"Academic score {'meets' if ok else 'is below'} the {c.academic_min_percent:g}% minimum"})

        if not hard:
            continue  # nothing we can honestly evaluate for this country

        if intake and c.intakes:
            if intake.lower() in (i.lower() for i in c.intakes):
                reasons.append({"status": "pass", "text": f"Has a {intake} intake"})
            else:
                reasons.append({"status": "partial", "text": f"No {intake} intake listed (offers {', '.join(c.intakes)})"})

        counts = {k: sum(1 for r in reasons if r["status"] == k) for k in ("pass", "partial", "fail")}
        tier = _tier(counts["pass"], counts["partial"], counts["fail"])
        if c.post_study_visa:
            reasons.append({"status": "info", "text": f"Post-study work: {c.post_study_visa}"})

        items.append({"id": c.id, "label": c.label, "icon": c.icon, "tier": tier, "tier_label": TIER_LABELS[tier],
                      "reasons": reasons, "_passed": counts["pass"]})

    items.sort(key=lambda i: (TIER_ORDER.index(i["tier"]), -i["_passed"], i["id"]))
    for i in items:
        del i["_passed"]
    return items


def check_eligibility(profile: dict, country: CountryRecord) -> dict | None:
    """Eligibility checks from facts we actually have. None when nothing can be evaluated."""
    checks = []
    english, academic = profile.get("english_score"), profile.get("academic_score")

    if english is not None and country.ielts_min is not None:
        ok = english >= country.ielts_min
        checks.append({"label": "English score", "ok": ok,
                       "detail": f"{english:g} vs {country.ielts_min:g} minimum"})
    if academic is not None and country.academic_min_percent is not None:
        ok = academic >= country.academic_min_percent
        checks.append({"label": "Academic score", "ok": ok,
                       "detail": f"{academic:g}% vs {country.academic_min_percent:g}% minimum"})
    if not checks:
        return None

    passed = sum(1 for c in checks if c["ok"])
    verdict = ("You meet the requirements we can check" if passed == len(checks)
               else "You meet some requirements" if passed else "You don't meet the minimums yet")
    if country.funds_required:
        checks.append({"label": "Proof of funds", "ok": False, "detail": country.funds_required})
    return {"verdict": verdict, "checks": checks}
