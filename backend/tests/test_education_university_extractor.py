"""The Admizz university page parser copies what the page states and leaves everything else empty (no guessing, no conversion)."""
from app.services.education_university_extractor import parse_university_page

URL = "https://admizzeducation.com/explore-universities/uk/test-university"


def _card(name, duration, amount, basis, intake="January"):
    return (f"<div><h3>{name}</h3><span>Duration</span><span>{duration}</span><span>Tuition</span><span>{amount}</span>"
            f"<span>{basis}</span><span>Intake</span><span>{intake}</span><a>Enquire about this course</a></div>")


def _page(cards_pg="", cards_ug="", cards_fd="", stated=None, academic_pg="<p>4 Year Bachelor's Degree : 55% or above</p>",
          ielts_pg="<p>IELTS</p><p>6.0 overall (5.5 in each component)</p>", verified=True):
    n = stated if stated is not None else (cards_pg + cards_ug + cards_fd).count("Enquire about this course")
    sections = ""
    for label, cards in (("Foundation", cards_fd), ("Undergraduate", cards_ug), ("Postgraduate", cards_pg)):
        if cards:
            sections += f"<h2>{label}</h2><span> courses</span><p>Tuition shown is the published fee for international students.</p>{cards}"
    return f"""<html><body><h1>Test University</h1><p>London, Greater London, United Kingdom</p>
<a>Talk to a Counsellor</a><p>Fees from</p><p>£10,000</p><p>Courses</p><p>{n}</p>{sections}
<h2>Scholarships</h2><p>Early Bird £1,000</p>
<h2>Academic requirements</h2><p>Admission criteria for Nepali students, by study level.</p>
<h3>Undergraduate</h3><p>Level 5 Diploma: 60% or above</p><h3>Postgraduate</h3>{academic_pg}
<h2>English language</h2><p>Accepted English tests and minimum scores.</p><h3>Postgraduate</h3>{ielts_pg}
<h3>Undergraduate</h3><p>IELTS</p><p>5.5 overall (5.5 in each component)</p>
<h2>Gap</h2><h2>Tuition fees</h2>
<h2>Intakes &amp; deadlines</h2><p>Intake</p><p>January</p><p>2027</p><p>September</p><p>2027</p>
<p>Showing intakes currently open through Admizz. Other intakes may be available — ask a counsellor.</p>
<h2>Campus locations</h2><p>London, Greater London, United Kingdom</p><a>View on map</a><p>Leeds, West Yorkshire, United Kingdom</p><a>View on map</a>
{'<p>Information last verified on</p><p>2026-10-07</p>' if verified else ''}</body></html>"""


def _parse(html):
    return parse_university_page(html, slug="test-university", country_id="uk", url=URL)


def test_reads_university_and_courses():
    p = _parse(_page(cards_pg=_card("MSc Data Science", "1 year", "£14,000", "total") + _card("MBA", "1 year", "£15,000", "total"),
                     cards_ug=_card("BSc Computing (Top-Up)", "1 year", "£12,500", "total")))
    assert p.university.name == "Test University" and p.university.city == "London"
    assert p.university.intakes == ["January", "September"] and p.last_verified == "2026-10-07"
    assert [c.name for c in p.courses] == ["BSc Computing (Top-Up)", "MSc Data Science", "MBA"]    # the page lists undergraduate first
    ug, pg = p.courses[0], p.courses[1]
    assert (pg.level, pg.duration_months, pg.tuition_per_year.amount, pg.tuition_per_year.currency) == ("master", 12, 14000, "GBP")
    assert (pg.ielts_min, pg.academic_min_percent, pg.intakes) == (6.0, 55.0, ["January"])
    assert (ug.level, ug.ielts_min, ug.academic_min_percent) == ("bachelor", 5.5, 60.0)
    assert pg.source == URL and "not verified by us" in p.university.source
    assert p.warnings == []


def test_foundation_uses_undergraduate_requirements_and_per_year_tuition():
    p = _parse(_page(cards_fd=_card("BSc Business with Foundation Year", "4 years", "£18,595", "per year")))
    c = p.courses[0]
    assert (c.level, c.duration_months, c.tuition_per_year.amount, c.ielts_min) == ("foundation", 48, 18595, 5.5)


def test_multi_year_total_is_not_divided():
    p = _parse(_page(cards_pg=_card("MSc Long", "18 months", "£10,395", "total")))
    assert p.courses[0].tuition_per_year is None
    assert any("not a clear per-year figure" in w for w in p.warnings)


def test_ambiguous_requirements_stay_empty():
    p = _parse(_page(cards_pg=_card("MSc A", "1 year", "£14,000", "total"),
                     academic_pg="<p>Term 1: degree pass</p><p>Term 2: degree 60%</p>",
                     ielts_pg="<p>IELTS (Term 1)</p><p>6.0 overall (5.5 in each)</p><p>IELTS (Term 2)</p><p>5.5 overall (5.5 in each)</p>"))
    assert p.courses[0].ielts_min is None and p.courses[0].academic_min_percent is None
    assert any("IELTS not read" in w for w in p.warnings) and any("academic requirement" in w for w in p.warnings)


def test_course_count_mismatch_and_missing_verified_date_are_reported():
    p = _parse(_page(cards_pg=_card("MSc A", "1 year", "£14,000", "total"), stated=3, verified=False))
    assert any("page states 3 courses, 1 were read" in w for w in p.warnings)
    assert any("last verified" in w for w in p.warnings) and p.last_verified is None


def test_duplicate_course_names_get_distinct_ids():
    p = _parse(_page(cards_pg=_card("MSc A", "1 year", "£14,000", "total") + _card("MSc A", "1 year", "£14,000", "total")))
    ids = [c.id for c in p.courses]
    assert len(set(ids)) == 2


def test_course_without_a_published_price_and_page_without_fees_from():
    html = _page(cards_pg=_card("MBA", "1 year", "Ask a counsellor", "")).replace("<p>Fees from</p><p>£10,000</p>", "")
    p = _parse(html)
    assert p is not None and p.courses[0].tuition_per_year is None
    assert any("no tuition amount (the page says 'Ask a counsellor" in w for w in p.warnings)


def test_course_list_coming_soon_is_labelled():
    html = ("<html><body><h1>Soon University</h1><a>Talk to a Counsellor</a><h2>Course list coming soon</h2>"
            "<p>We're adding this university's courses and fees.</p></body></html>")
    p = _parse(html)
    assert p.courses == [] and any("coming soon" in w for w in p.warnings)


def test_not_a_university_page():
    assert _parse("<html><body><h1>Not found</h1></body></html>") is None
