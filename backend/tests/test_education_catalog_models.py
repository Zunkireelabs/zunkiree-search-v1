"""University / Course models and the catalog provider seam. The repository ships NO universities or courses: the records
below exist only inside these tests, to prove the models validate and a real source can plug in later."""
import json
import logging

import pytest
from pydantic import ValidationError

from app.services import education_catalog
from app.services.education_catalog import (
    CATALOG_DIR, Catalog, CatalogProvider, CountryRecord, JsonFileCatalogProvider, get_catalog, load_catalog_file,
    register_catalog, set_catalog_providers,
)
from app.services.education_catalog_models import Course, University
from app.services.money import Money


@pytest.fixture(autouse=True)
def _isolated_catalog_state(monkeypatch):
    monkeypatch.setattr(education_catalog, "_registry", {})
    monkeypatch.setattr(education_catalog, "_EMPTY", {})
    monkeypatch.setattr(education_catalog, "_providers", [JsonFileCatalogProvider()])


def uni(**kw) -> dict:
    return {**dict(id="u1", name="Test University", country_id="uk"), **kw}


def course(**kw) -> dict:
    return {**dict(id="c1", university_id="u1", name="MSc Testing", level="master"), **kw}


def catalog(**kw) -> Catalog:
    base = dict(site_id="t", currency="NPR", countries=[CountryRecord(id="uk", label="U.K."), CountryRecord(id="au", label="Australia")])
    return Catalog(**{**base, **kw})


# ---- nothing ships ----

def test_a_catalog_has_no_universities_or_courses_unless_a_source_supplies_them():
    c = Catalog(site_id="x")
    assert c.universities == [] and c.courses == []


def test_the_sample_catalog_file_ships_no_universities_or_courses():
    sample = load_catalog_file(CATALOG_DIR / "admizz-test.json")
    assert sample.universities == [] and sample.courses == []
    assert not any(k in json.loads((CATALOG_DIR / "admizz-test.json").read_text()) for k in ("universities", "courses"))


def test_the_sample_catalog_is_marked_as_placeholder_data():
    assert load_catalog_file(CATALOG_DIR / "admizz-test.json").is_placeholder is True
    assert Catalog(site_id="x").is_placeholder is False          # status defaults to verified


# ---- the models ----

def test_valid_records_build():
    c = catalog(universities=[uni(city="London", intakes=["September"], source="tenant spreadsheet 2026-09")],
                courses=[course(field_of_study="Business", duration_months=12, ielts_min=6.5, academic_min_percent=60,
                                tuition_per_year=Money(2_000_000, "npr"), intakes=["September"])])
    assert c.get_course("c1").tuition_per_year.format() == "NPR 20,00,000"
    assert c.get_university("u1").source.startswith("tenant")


@pytest.mark.parametrize("bad", [
    uni(id=""), uni(name=""), uni(country_id=""),
])
def test_a_university_needs_an_id_a_name_and_a_country(bad):
    with pytest.raises(ValidationError):
        University(**bad)


@pytest.mark.parametrize("bad", [
    course(level="diploma"),
    course(duration_months=0), course(duration_months=-6),
    course(ielts_min=10), course(ielts_min=-1),
    course(academic_min_percent=101),
    course(tuition_per_year=Money(-1, "NPR")),
    course(name=""),
])
def test_a_course_rejects_nonsense_values(bad):
    with pytest.raises(ValidationError):
        Course(**bad)


def test_everything_a_source_might_not_know_is_optional():
    c = Course(**course())
    assert (c.field_of_study, c.duration_months, c.tuition_per_year, c.ielts_min, c.academic_min_percent, c.source) == (None,) * 6
    assert c.intakes == []


def test_tuition_normalises_its_currency_like_every_other_amount():
    assert Course(**course(tuition_per_year=Money(20000, "£"))).tuition_per_year.currency == "GBP"
    assert Course.model_validate(course(tuition_per_year={"amount": 5000, "currency": "$"})).tuition_per_year == Money(5000, "USD")


# ---- internal consistency: a catalog is whole or it is rejected ----

def test_a_university_in_an_unknown_country_is_rejected():
    with pytest.raises(ValidationError, match="unknown country"):
        catalog(universities=[uni(country_id="atlantis")])


def test_a_course_at_an_unknown_university_is_rejected():
    with pytest.raises(ValidationError, match="unknown university"):
        catalog(universities=[uni()], courses=[course(university_id="nope")])


@pytest.mark.parametrize("kwargs", [
    dict(universities=[uni(), uni(name="Other")]),
    dict(universities=[uni()], courses=[course(), course(name="Other")]),
    dict(countries=[CountryRecord(id="uk", label="A"), CountryRecord(id="uk", label="B")]),
])
def test_duplicate_ids_are_rejected(kwargs):
    with pytest.raises(ValidationError, match="duplicate"):
        catalog(**kwargs)


def test_lookups():
    c = catalog(universities=[uni(), uni(id="u2", country_id="au")], courses=[course(), course(id="c2", university_id="u2")])
    assert [u.id for u in c.universities_in("uk")] == ["u1"] and c.universities_in("ca") == []
    assert [x.id for x in c.courses_at("u2")] == ["c2"] and c.courses_at("nope") == []
    assert c.get_university("nope") is None and c.get_course("nope") is None


# ---- money in a catalog that mixes currencies ----

def test_tuition_in_another_currency_than_the_students_budget_is_not_comparable():
    c = catalog(universities=[uni()], courses=[course(tuition_per_year=Money(20000, "GBP"))])
    budget = Money(2_000_000, c.currency)
    assert c.get_course("c1").tuition_per_year.compare(budget) is None      # no exchange rate, so no guess


def test_tuition_in_the_same_currency_compares():
    c = catalog(universities=[uni()], courses=[course(tuition_per_year=Money(1_500_000, "NPR"))])
    assert c.get_course("c1").tuition_per_year.compare(Money(2_000_000, c.currency)) == -1


# ---- loading from a file (what a JSON source does) ----

def test_a_catalog_file_with_universities_and_courses_loads(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"site_id": "t", "currency": "NPR", "countries": [{"id": "uk", "label": "U.K."}],
                                "universities": [uni()], "courses": [course(tuition_per_year={"amount": 100, "currency": "npr"})]}))
    loaded = load_catalog_file(path)
    assert loaded.get_course("c1").tuition_per_year == Money(100, "NPR")


def test_an_inconsistent_catalog_file_is_refused_and_logged(tmp_path, caplog):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"site_id": "t", "countries": [{"id": "uk", "label": "U.K."}], "universities": [uni(country_id="zz")]}))
    with caplog.at_level(logging.ERROR):
        assert load_catalog_file(path) is None
    assert any("invalid" in r.getMessage() for r in caplog.records)


def test_an_inconsistent_catalog_means_an_empty_one_so_no_half_wrong_card_is_ever_shown(tmp_path, monkeypatch):
    (tmp_path / "bad.json").write_text(json.dumps({"site_id": "bad", "countries": [{"id": "uk", "label": "U.K."}],
                                                    "universities": [uni(country_id="zz")]}))
    set_catalog_providers([JsonFileCatalogProvider(tmp_path)])
    got = get_catalog("bad")
    assert got.countries == [] and got.universities == []


# ---- the provider seam ----

class FakeProvider:
    def __init__(self, catalogs=None, error=None):
        self.catalogs, self.error, self.calls = catalogs or {}, error, 0

    def load(self, site_id):
        self.calls += 1
        if self.error:
            raise self.error
        return self.catalogs.get(site_id)


def test_get_catalog_still_loads_the_sample_file_and_returns_empty_for_strangers():
    assert get_catalog("admizz-test").countries
    nobody = get_catalog("nobody-here")
    assert nobody.countries == [] and nobody.site_id == "nobody-here"


def test_a_registered_catalog_takes_precedence_over_every_provider():
    provider = FakeProvider({"s": catalog(site_id="s")})
    set_catalog_providers([provider])
    mine = catalog(site_id="s", currency="GBP")
    register_catalog(mine)
    assert get_catalog("s") is mine and provider.calls == 0


def test_a_custom_provider_plugs_in_and_the_result_is_cached():
    provider = FakeProvider({"s": catalog(site_id="s")})
    set_catalog_providers([provider])
    first = get_catalog("s")
    assert first.site_id == "s" and get_catalog("s") is first and provider.calls == 1


def test_the_first_provider_with_a_catalog_wins_and_later_ones_are_not_asked():
    a, b = FakeProvider({"s": catalog(site_id="s", currency="GBP")}), FakeProvider({"s": catalog(site_id="s")})
    set_catalog_providers([a, b])
    assert get_catalog("s").currency == "GBP" and b.calls == 0


def test_a_provider_with_nothing_falls_through_to_the_next():
    a, b = FakeProvider(), FakeProvider({"s": catalog(site_id="s")})
    set_catalog_providers([a, b])
    assert get_catalog("s").site_id == "s" and (a.calls, b.calls) == (1, 1)


def test_a_failing_provider_is_logged_and_skipped_never_fatal(caplog):
    broken, healthy = FakeProvider(error=RuntimeError("db down")), FakeProvider({"s": catalog(site_id="s")})
    set_catalog_providers([broken, healthy])
    with caplog.at_level(logging.ERROR):
        assert get_catalog("s").site_id == "s"
    assert any("FakeProvider failed" in r.getMessage() for r in caplog.records)


def test_when_every_provider_fails_the_chat_still_gets_an_empty_catalog():
    set_catalog_providers([FakeProvider(error=RuntimeError("x"))])
    assert get_catalog("s").countries == []


def test_the_json_provider_only_builds_paths_from_plain_ids(tmp_path):
    (tmp_path / "ok.json").write_text(json.dumps({"site_id": "ok", "countries": [{"id": "uk", "label": "U.K."}]}))
    (tmp_path.parent / "escape.json").write_text(json.dumps({"site_id": "escape"}))
    p = JsonFileCatalogProvider(tmp_path)
    assert p.load("ok").site_id == "ok"
    for evil in ("../escape", "..", "a/b", "a\\b", "", "ok.json", "ok\x00"):
        assert p.load(evil) is None, evil


def test_providers_satisfy_the_protocol():
    def takes(p: CatalogProvider) -> CatalogProvider:
        return p
    assert takes(JsonFileCatalogProvider()) and takes(FakeProvider())


def _write_site(tmp_path, records=None, raw=None):
    (tmp_path / "t-site.json").write_text(json.dumps({"site_id": "t-site", "status": "PLACEHOLDER", "currency": "$",
                                                      "countries": [{"id": "uk", "label": "U.K."}]}))
    if records is not None or raw is not None:
        (tmp_path / "t-site.uk.json").write_text(raw if raw is not None else json.dumps(records))
    return JsonFileCatalogProvider(tmp_path).load("t-site")


UK_RECORDS = {"universities": [{"id": "u1", "name": "U One", "country_id": "uk"}],
              "courses": [{"id": "u1--c", "university_id": "u1", "name": "MSc C", "level": "master",
                           "tuition_total": {"amount": 16200, "currency": "GBP"}, "tuition_note": "from £16,200 total"}]}


def test_record_files_are_merged_into_the_tenant_catalog(tmp_path):
    c = _write_site(tmp_path, UK_RECORDS)
    assert [u.id for u in c.universities] == ["u1"] and c.courses[0].tuition_total.amount == 16200
    assert c.courses[0].tuition_per_year is None and c.is_placeholder     # the countries are still sample data
    assert [x.id for x in c.countries] == ["uk"]


def test_an_invalid_record_file_is_skipped_and_the_countries_still_load(tmp_path):
    for bad in ({"universities": [{"id": "u1", "name": "X", "country_id": "nowhere"}]}, "not json"):
        c = _write_site(tmp_path, bad) if isinstance(bad, dict) else _write_site(tmp_path, raw=bad)
        assert c is not None and c.universities == [] and [x.id for x in c.countries] == ["uk"]


def test_a_negative_total_is_rejected(tmp_path):
    bad = {"universities": UK_RECORDS["universities"], "courses": [{**UK_RECORDS["courses"][0], "tuition_total": {"amount": -1, "currency": "GBP"}}]}
    assert _write_site(tmp_path, bad).courses == []
