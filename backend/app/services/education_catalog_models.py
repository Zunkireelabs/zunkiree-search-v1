"""
Normalized University and Course records for the education catalog.

These are the shapes a real catalog (a database, an API, a verified spreadsheet import) must produce. UI code is written
against these models, not against any one source, so replacing the sample data never touches the UI layer.

Nothing here is data. The only records the repository ships are the unverified Admizz UK website records in
`app/data/education_catalogs/admizz-test.uk.json` (see scripts/extract_education_uk_catalog.py). Every field that a source might not know is
optional, and a card is only built from what is present. Tuition is `Money` (amount + currency) in the record's own
currency; there is no conversion, so a tuition in a different currency than the student's budget is simply not comparable
(`Money.compare` returns None) and a caller treats that as "unknown".
"""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.money import Money

StudyLevel = Literal["foundation", "bachelor", "master", "phd"]


def _non_negative(money: Money | None) -> Money | None:
    if money is not None and money.amount < 0:
        raise ValueError("tuition cannot be negative")
    return money


class University(BaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    country_id: str = Field(min_length=1)       # must be a country of the same catalog
    city: str | None = None
    website: str | None = None
    intakes: list[str] = []
    source: str | None = None                   # where this record came from, for the "how do you know" question


class Course(BaseModel):
    id: str = Field(min_length=1)
    university_id: str = Field(min_length=1)    # must be a university of the same catalog
    name: str = Field(min_length=1)
    level: StudyLevel
    field_of_study: str | None = None
    duration_months: int | None = Field(default=None, gt=0)
    tuition_per_year: Money | None = None
    tuition_total: Money | None = None          # the whole-course fee when the source states only a total for a multi-year course
    tuition_note: str | None = None             # the source's own wording when it is more than a plain figure ("from £X total · then ...")
    intakes: list[str] = []
    ielts_min: float | None = Field(default=None, ge=0, le=9)
    academic_min_percent: float | None = Field(default=None, ge=0, le=100)
    source: str | None = None

    _tuition_ok = field_validator("tuition_per_year", "tuition_total")(_non_negative)
