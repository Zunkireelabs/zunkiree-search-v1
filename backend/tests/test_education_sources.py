"""The source registry is data-only: absolute links to public Admizz pages with their provenance dates, all `verified: false`.
It never holds a university, course, fee or requirement. Only https links on the approved host may ever be shown, whatever
the registry file or a retrieved knowledge-base chunk says."""
import json
import re

import pytest

from app.services import education_sources as src
from app.services.education_sources import (
    Resource, SourceRegistry, category_for_question, is_allowed_url, link_line, load_sources_file, resources_for,
)

HOST = "https://admizzeducation.com"


def _res(**kw):
    base = dict(id="r1", country="uk", url=f"{HOST}/study-in-the-uk", title="Study in the UK", category="guide", kind="guide")
    return Resource(**{**base, **kw})


@pytest.fixture(autouse=True)
def _clean():
    src.reset_sources()
    yield
    src.reset_sources()


# --- the URL allow-list ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    f"{HOST}/study-in-the-uk",
    f"{HOST}/answers/uk-student-visa-fee-nepal",
    f"{HOST}/",
    f"{HOST}/test-prep/",
])
def test_approved_urls(url):
    assert is_allowed_url(url)


@pytest.mark.parametrize("url", [
    "http://admizzeducation.com/study-in-the-uk",              # not https
    "https://www.admizzeducation.com/study-in-the-uk",          # not the exact approved host
    "https://admizzeducation.com.evil.com/x",                   # look-alike host
    "https://evil.com/admizzeducation.com",
    "https://user@admizzeducation.com/x",                       # userinfo
    "https://admizzeducation.com:8443/x",                       # port
    "https://admizzeducation.com/x?next=https://evil.com",      # query (open-redirect shape)
    "https://admizzeducation.com/x#frag",
    "https://admizzeducation.com/x y",
    "https://admizzeducation.com/x(1)",                         # would break a Markdown link
    "https://admizzeducation.com/x\"onmouseover=\"y",
    "javascript:alert(1)",
    "//admizzeducation.com/x",
    "/study-in-the-uk",
    "",
    None,
    42,
])
def test_rejected_urls(url):
    assert is_allowed_url(url) is False


def test_resource_rejects_an_unapproved_url():
    with pytest.raises(ValueError):
        _res(url="http://admizzeducation.com/x")


# --- loading ---------------------------------------------------------------------------------------------------------

def _file(tmp_path, doc):
    path = tmp_path / "t.json"
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc))
    return path


def test_valid_registry_loads(tmp_path):
    entry = {"id": "uk-guide", "country": "uk", "url": f"{HOST}/study-in-the-uk", "title": "Study in the UK",
             "category": "guide", "kind": "guide", "sitemap_lastmod": "2026-10-08", "published": None, "checked": None,
             "verified": False, "ingested_at": None}
    reg = load_sources_file(_file(tmp_path, {"site_id": "t", "resources": [entry]}))
    assert reg and [r.id for r in reg.resources] == ["uk-guide"]


@pytest.mark.parametrize("doc", ["not json", "[]", {"site_id": "t"}, {"site_id": "t", "resources": "x"}, {"resources": []}])
def test_invalid_registry_file_is_ignored_not_fatal(tmp_path, doc):
    assert load_sources_file(_file(tmp_path, doc)) is None


def test_one_bad_entry_is_dropped_and_the_rest_survive(tmp_path, caplog):
    good = {"id": "a", "country": "uk", "url": f"{HOST}/study-in-the-uk", "title": "A", "category": "guide", "kind": "guide"}
    bad_url = {**good, "id": "b", "url": "https://evil.com/x"}
    bad_cat = {**good, "id": "c", "category": "fees"}
    bad_date = {**good, "id": "d", "checked": "October 2026"}
    reg = load_sources_file(_file(tmp_path, {"site_id": "t", "resources": [good, bad_url, bad_cat, bad_date]}))
    assert [r.id for r in reg.resources] == ["a"]
    assert "dropped" in caplog.text


def test_duplicate_ids_keep_the_first(tmp_path):
    e = {"id": "a", "country": "uk", "url": f"{HOST}/study-in-the-uk", "title": "A", "category": "guide", "kind": "guide"}
    reg = load_sources_file(_file(tmp_path, {"site_id": "t", "resources": [e, {**e, "title": "B"}]}))
    assert [r.title for r in reg.resources] == ["A"]


@pytest.mark.parametrize("field,value", [
    ("published", "2026-13-40"), ("published", "05/10/2026"), ("checked", "Oct 2026"), ("sitemap_lastmod", "yesterday"),
])
def test_dates_must_be_real_iso_dates_never_free_text(field, value):
    with pytest.raises(ValueError):
        _res(**{field: value})


def test_missing_optional_fields_are_fine():
    r = _res()
    assert r.published is None and r.checked is None and r.sitemap_lastmod is None and r.verified is False


def test_a_registry_can_never_mark_a_page_verified():
    with pytest.raises(ValueError):
        _res(verified=True)      # promoting website text to "verified" is a separate, human decision, not a data flag here


def test_site_id_is_never_turned_into_a_path(tmp_path):
    (tmp_path / "x.json").write_text("{}")
    provider = src.JsonFileSourceProvider(tmp_path)
    for bad in ("../x", "a/b", "", "x.json", None):
        assert provider.load(bad) is None


def test_unknown_tenant_gets_an_empty_registry():
    assert src.get_sources("nobody").resources == []


def test_the_shipped_registry_is_valid_and_data_only():
    reg = src.get_sources("admizz-test")
    assert len(reg.resources) >= 30
    assert all(r.verified is False and r.ingested_at is None for r in reg.resources)
    assert all(is_allowed_url(r.url) for r in reg.resources)
    assert {r.country for r in reg.resources if r.country} <= {"uk", "us", "au", "ca", "de"}   # the catalog's countries
    # no figure of any kind: titles are descriptions, never amounts
    assert not [r.title for r in reg.resources if re.search(r"[£$€₹]|\b(NPR|Rs)\b|\d{1,3},\d{3}", r.title)]
    raw = json.loads((src.SOURCES_DIR / "admizz-test.json").read_text())
    allowed = {"id", "country", "url", "title", "category", "kind", "sitemap_lastmod", "published", "checked", "verified", "ingested_at"}
    assert all(set(e) <= allowed for e in raw["resources"])             # no fee/requirement/course fields can hide in here


def test_dated_answer_pages_carry_their_dates_and_nothing_is_invented():
    reg = src.get_sources("admizz-test")
    fee = next(r for r in reg.resources if r.id == "uk-visa-fee")
    assert (fee.published, fee.checked, fee.sitemap_lastmod) == ("2026-10-05", "2026-10", "2026-10-08")   # three different dates
    guide = next(r for r in reg.resources if r.id == "uk-guide")
    assert guide.published is None and guide.checked is None            # the page states neither: left empty, not guessed


# --- selection -------------------------------------------------------------------------------------------------------

def _registry():
    return SourceRegistry(site_id="t", resources=[
        _res(id="uk-g", kind="guide", category="guide"),
        _res(id="uk-a1", kind="answer", category="visa", url=f"{HOST}/answers/uk-student-visa-fee-nepal", title="UK Student Visa Fee and Health Surcharge"),
        _res(id="uk-a2", kind="answer", category="visa", url=f"{HOST}/answers/uk-student-visa-bank-balance-nepal", title="UK Student Visa Bank Balance from Nepal"),
        _res(id="uk-c", kind="article", category="cost", url=f"{HOST}/uk-cost", title="Cost of Studying in UK"),
        _res(id="ca-g", country="ca", kind="guide", category="guide", url=f"{HOST}/study-in-canada", title="Study in Canada"),
        _res(id="tp", country=None, kind="service", category="test_prep", url=f"{HOST}/test-prep", title="Test Preparation"),
    ])


def test_selection_by_country_and_category_puts_answers_first():
    src.register_sources(_registry())
    assert [r.id for r in resources_for("t", "uk", "visa")] == ["uk-a1", "uk-a2"]
    assert [r.id for r in resources_for("t", "uk")] == ["uk-a1", "uk-a2", "uk-g", "uk-c"]    # answer, guide, article


def test_unknown_country_or_category_returns_nothing_not_a_guess():
    src.register_sources(_registry())
    assert resources_for("t", "zz") == []
    assert resources_for("t", "uk", "scholarship") == []
    assert resources_for("t", None) == []
    assert resources_for("nobody", "uk") == []


def test_shared_resources_are_only_returned_when_asked_for():
    src.register_sources(_registry())
    assert resources_for("t", "uk", "test_prep") == []
    assert [r.id for r in resources_for("t", "uk", "test_prep", include_shared=True)] == ["tp"]
    assert [r.id for r in resources_for("t", None, "test_prep", include_shared=True)] == ["tp"]


def test_tenants_do_not_see_each_others_sources():
    src.register_sources(_registry())
    src.register_sources(SourceRegistry(site_id="other", resources=[]))
    assert resources_for("other", "uk") == []
    assert resources_for("t", "uk")


# --- intent / question -> category ------------------------------------------------------------------------------------

@pytest.mark.parametrize("question,category", [
    ("how do I prepare for ielts", "test_prep"),
    ("do you offer pte coaching classes?", "test_prep"),
    ("any scholarships for uk", "scholarship"),
    ("what is the uk student visa fee", "visa"),
    ("how much is the blocked account for germany", "visa"),
    ("what are the tuition fees in canada", "cost"),
    ("how much will living cost", "cost"),
    ("what documents do i need to apply", "application"),
    ("when is the january intake", "application"),
    ("minimum ielts requirement for canada", "application"),
])
def test_question_category(question, category):
    assert category_for_question(question) == category


@pytest.mark.parametrize("question", ["hello", "tell me about yourself", "ok thanks", "", "7 is my english score"])
def test_no_category_means_no_link(question):
    assert category_for_question(question) is None


# --- the link line ---------------------------------------------------------------------------------------------------

def test_link_line_is_a_plain_markdown_link():
    assert link_line(_res()) == f"More on Admizz: [Study in the UK]({HOST}/study-in-the-uk)"


def test_checked_date_appears_only_when_the_source_states_it():
    dated = _res(url=f"{HOST}/answers/uk-student-visa-fee-nepal", title="UK Student Visa Fee", kind="answer", category="visa",
                 published="2026-10-05", checked="2026-10", sitemap_lastmod="2026-10-08")
    assert link_line(dated).endswith("(checked October 2026)")
    assert "5 October" not in link_line(dated) and "2026-10-08" not in link_line(dated)    # published/lastmod are not "checked"
    assert "checked" not in link_line(_res(published="2026-10-05", sitemap_lastmod="2026-10-08"))
    assert link_line(_res(checked="2026-10-12")).endswith("(checked 12 October 2026)")


def test_titles_cannot_break_out_of_the_markdown_link():
    line = link_line(_res(title="Study ](https://evil.com) [click me"))
    assert line.count("](") == 1 and line.count("[") == 1 and "evil.com" not in line
    assert line.endswith(f"]({HOST}/study-in-the-uk)")


def test_a_title_with_a_line_break_is_rejected_by_the_registry():
    with pytest.raises(ValueError):
        _res(title="two\nlines")


def test_a_link_line_is_never_built_for_an_unapproved_url():
    r = _res()
    object.__setattr__(r, "url", "https://evil.com/x")         # even if validation were bypassed, nothing is emitted
    assert link_line(r) == ""
