"""The shared extractor (app.utils.crawling.extract_text_from_html) deletes every element whose class or id merely CONTAINS "ad",
"nav", "menu", "header"... and Tailwind's `leading-relaxed` contains "ad", so on the Admizz site it removes the paragraphs and keeps
footer boilerplate. The Admizz page extractor reads the page the way the page is built: headings with their text, a question with
its answer, the sources and checked line kept, and the related-articles, call-to-action and statistic panels left out. These
fixtures copy the structures of the live pages (answer page, country guide, test-prep page) without any network."""
import re

import pytest

from app.services.education_page_extractor import ExtractedPage, extract_page
from app.utils.chunking import chunk_text
from app.utils.crawling import extract_text_from_html as shared_extract

P = 'class="text-base text-gray-dark leading-relaxed mb-4"'      # the real paragraph class: contains "ad" (le-AD-ing)

ANSWER_PAGE = f"""<html><head><title>UK Student Visa Fee and Health Surcharge: Short Answer</title></head><body>
<header class="site-header"><nav class="main-nav"><a href="/study-in-the-uk">Study in the UK</a></nav></header>
<main>
 <section class="bg-gradient-to-r header-hero"><div>
   <div class="flex gap-2"><a>UK</a><a>Visa Guides</a><a>Nepal</a></div>
   <h1 class="text-2xl font-bold">How Much Is the UK Student Visa Fee and Health Surcharge?</h1>
   <p class="mt-3 text-sm">By Admizz Education · October 5, 2026</p></div></section>
 <article class="py-12"><div class="max-w-7xl"><div class="flex"><div class="flex-1 max-w-3xl">
   <section class="mb-8"><p class="uppercase">Quick Answer</p>
     <p class="leading-[1.7]">A UK Student visa applied for from outside the UK costs £558. You also pay the Immigration Health Surcharge of £776 per year of visa.</p></section>
   <div><h2>The details</h2><ul class="list-disc"><li class="leading-relaxed"><strong>Visa fee:</strong> £558 from outside the UK.</li>
     <li class="leading-relaxed"><strong>Health surcharge:</strong> £776 per year for students, paid in full when you apply.</li></ul>
     <p {P}>See the <a href="/uk-student-visa-cost-2027">full UK student visa cost breakdown</a>.</p></div>
   <div><h2>Related guides</h2><ul><li>UK student visa cost 2027</li><li>Top education consultancy in Nepal</li></ul></div>
   <div><h2>Sources</h2><ul><li><a href="https://www.gov.uk/student-visa/how-much-it-costs">GOV.UK: Student visa, how much it costs</a></li>
     <li><a href="https://www.gov.uk/healthcare-immigration-application/how-much-pay">GOV.UK: Immigration Health Surcharge</a></li>
     <li><a href="http://insecure.example/x">Insecure</a></li><li><a href="https://facebook.com/admizz">Facebook</a></li></ul>
     <p {P}>Checked in October 2026. Rules change, so confirm on the official site before you apply.</p></div>
   <section><h2>Frequently Asked Questions</h2>
     <div><h3>How is the health surcharge calculated?</h3><p {P}>It depends on how long your visa lasts. For a visa of 18 months or less you pay the yearly cost plus half.</p></div>
     <div><h3>Are the visa fee and the bank balance the same thing?</h3><p {P}>No. The visa fee and health surcharge are paid to the Home Office. The bank balance is separate.</p></div></section>
 </div><div class="lg:hidden"><p class="font-bold">Book a Free Counseling Session</p></div></div></div></article>
 <section class="py-14"><h2>Related Articles</h2><p>Explore more articles on similar topics</p>
   <div><a><h3>Top Education Consultancy in Nepal</h3><p>Compare consultancies before you choose.</p></a></div></section>
 <section class="py-14"><span>Accepting Applications</span><h2>Ready to Build Your Global Career?</h2><p>Let our expert counselors guide you.</p>
   <div><span>24hr Response</span><span>Average reply time</span></div><a>Email Us</a></section>
</main><footer><p>Copyright Admizz</p></footer></body></html>"""

GUIDE_PAGE = f"""<html><head><title>Study in the UK - Admizz Education</title></head><body><main>
 <section class="hero"><p>Shape Your Future at World-Class Universities</p><h1>STUDY IN THE UK</h1>
   <p class="leading-relaxed">Choosing the UK for higher studies opens doors to international exposure and recognised qualifications.</p><a>Learn More</a></section>
 <section class="bg-white py-5"><div><span>London</span><span>Capital</span></div><div><span>English</span><span>Language</span></div><div><span>+44</span><span>Dialing Code</span></div></section>
 <section class="bg-off-white py-8"><div><span>2,000+</span><span>Students enrolled</span></div><div><span>95%</span><span>Approval Rate</span></div></section>
 <section class="py-16"><h2>Admission Requirements for Studying in the UK</h2>
   <h3>Documents Required for Admission</h3><ul><li class="leading-relaxed">Academic transcripts and certificates</li><li>Passport copy</li></ul>
   <h3>Academic Intakes in the UK</h3><h4>September / Fall Intake (Major Intake)</h4><p {P}>The largest intake, with the widest choice of courses.</p>
   <h4>January / Winter Intake</h4><p {P}>A smaller intake with fewer courses.</p></section>
 <section class="py-16"><h2>UK Student Visa Process</h2><h3>1 . Choose Course &amp; University</h3><p {P}>Pick a course and shortlist universities.</p>
   <h3>2 . Submit Application</h3><p {P}>Apply with your documents.</p></section>
 <div class="scroll-mt-32"><h2>Everything You Need to Know</h2>
   <div><h3>Is the UK a good place for international students?</h3><button>Show answer</button><p {P}>Yes. The UK offers globally recognised degrees and a post-study work route.</p></div></div>
 <section class="py-16"><h2>Study Abroad Insights</h2><h3>Some blog title</h3><p>Blog teaser text.</p></section>
</main></body></html>"""


def _text(page: ExtractedPage) -> str:
    return page.text


# --- the bug that motivated this -----------------------------------------------------------------------------------------

def test_the_shared_extractor_still_loses_the_paragraphs_and_stays_unchanged_for_other_tenants():
    _, content = shared_extract(f'<html><body><main><p {P}>The answer paragraph.</p></main></body></html>')
    assert "The answer paragraph." not in content          # pinned: this is the shared behaviour; this task does not touch it


def test_class_names_that_contain_ad_nav_menu_or_header_do_not_delete_content():
    html = ('<html><body><main><h2>Costs</h2>'
            '<p class="text-base leading-relaxed">Tuition is shown on the course page.</p>'
            '<div class="header-title heading lead address read-more menu-card nav-pill"><p>Living costs depend on the city.</p></div>'
            '<ul class="nav-list"><li class="advice-item">Budget for rent and food.</li></ul></main></body></html>')
    text = extract_page(html).text
    for kept in ("Tuition is shown on the course page.", "Living costs depend on the city.", "Budget for rent and food."):
        assert kept in text


# --- an answer page ---------------------------------------------------------------------------------------------------------

def test_the_answer_and_its_supporting_context_are_kept():
    page = extract_page(ANSWER_PAGE)
    for kept in ("How Much Is the UK Student Visa Fee and Health Surcharge?", "By Admizz Education · October 5, 2026",
                 "A UK Student visa applied for from outside the UK costs £558.", "The details",
                 "Visa fee: £558 from outside the UK.", "Health surcharge: £776 per year for students, paid in full when you apply.",
                 "See the full UK student visa cost breakdown."):
        assert kept in page.text, kept


def test_inline_formatting_does_not_split_a_line():
    assert "Visa fee: £558 from outside the UK." in extract_page(ANSWER_PAGE).text      # <strong>Visa fee:</strong> £558 ...
    assert "Visa fee:\n£558" not in extract_page(ANSWER_PAGE).text


def test_sources_and_the_checked_statement_are_kept():
    text = extract_page(ANSWER_PAGE).text
    assert "GOV.UK: Student visa, how much it costs" in text and "GOV.UK: Immigration Health Surcharge" in text
    assert "Checked in October 2026. Rules change, so confirm on the official site before you apply." in text


def test_navigation_footer_breadcrumbs_related_content_and_calls_to_action_are_left_out():
    page = extract_page(ANSWER_PAGE)
    for gone in ("Study in the UK", "Copyright Admizz", "Related guides", "Top education consultancy in Nepal", "Related Articles",
                 "Explore more articles", "Compare consultancies", "Ready to Build Your Global Career?", "24hr Response",
                 "Accepting Applications", "Email Us", "Book a Free Counseling Session"):
        assert gone not in page.text, gone
    assert "UK\nVisa Guides" not in page.text and "Visa Guides" not in page.text            # the breadcrumb tags
    assert {"Related guides", "Related Articles", "Ready to Build Your Global Career?"} <= set(page.dropped)


def test_a_dropped_section_drops_its_subheadings_too_and_the_next_section_survives():
    html = ("<main><h2>Related Articles</h2><h3>Card title</h3><p>Card text here.</p><h2>Real section</h2><p>Real text lives here.</p></main>")
    text = extract_page(html).text
    assert "Card title" not in text and "Card text here." not in text and "Real text lives here." in text


# --- questions stay with their answers ----------------------------------------------------------------------------------------

def test_every_faq_block_holds_the_question_and_its_answer_together_under_its_section():
    blocks = extract_page(ANSWER_PAGE).blocks
    faq = [b for b in blocks if b.startswith("Frequently Asked Questions › ")]
    assert len(faq) == 2
    assert faq[0].split("\n")[0] == "Frequently Asked Questions › How is the health surcharge calculated?"
    assert "For a visa of 18 months or less you pay the yearly cost plus half." in faq[0]
    assert faq[1].startswith("Frequently Asked Questions › Are the visa fee and the bank balance the same thing?")
    assert "The bank balance is separate." in faq[1] and "18 months" not in faq[1]


def test_a_nested_heading_carries_its_parents_for_context():
    blocks = extract_page(GUIDE_PAGE).blocks
    assert any(b.startswith("Admission Requirements for Studying in the UK › Documents Required for Admission\n") for b in blocks)
    assert any(b.startswith("Admission Requirements for Studying in the UK › Academic Intakes in the UK › September / Fall Intake (Major Intake)\n")
               for b in blocks)


def test_a_heading_with_no_text_of_its_own_adds_no_empty_block():
    assert not [b for b in extract_page(GUIDE_PAGE).blocks if "\n" not in b and b.startswith("Admission Requirements")]


# --- a country guide ---------------------------------------------------------------------------------------------------------

def test_statistic_panels_and_marketing_numbers_are_left_out_but_the_description_stays():
    text = extract_page(GUIDE_PAGE).text
    for gone in ("London", "Dialing Code", "2,000+", "95%", "Approval Rate", "Learn More", "Blog teaser text.", "Some blog title"):
        assert gone not in text, gone
    assert "Choosing the UK for higher studies opens doors" in text and "STUDY IN THE UK" in text


def test_numbered_steps_keep_their_text():
    text = extract_page(GUIDE_PAGE).text
    assert "1. Choose Course & University" in text and "Pick a course and shortlist universities." in text
    assert "Apply with your documents." in text


def test_a_faq_accordion_button_label_is_not_mistaken_for_content():
    text = extract_page(GUIDE_PAGE).text
    assert "Is the UK a good place for international students?" in text and "Show answer" not in text
    assert "Yes. The UK offers globally recognised degrees" in text


# --- references --------------------------------------------------------------------------------------------------------------

def test_outbound_references_are_collected_for_the_manifest_not_put_into_the_text():
    page = extract_page(ANSWER_PAGE)
    assert [(r["text"], r["url"]) for r in page.references] == [
        ("GOV.UK: Student visa, how much it costs", "https://www.gov.uk/student-visa/how-much-it-costs"),
        ("GOV.UK: Immigration Health Surcharge", "https://www.gov.uk/healthcare-immigration-application/how-much-pay")]
    assert "https://" not in page.text                      # no web address reaches the chunk text the AI reads


def test_social_internal_insecure_and_script_links_are_never_references():
    html = ('<main><h2>Sources</h2><a href="https://facebook.com/x">f</a><a href="/study-in-the-uk">internal</a>'
            '<a href="http://gov.uk/x">http</a><a href="javascript:alert(1)">js</a><a href="https://admizzeducation.com/x">own</a>'
            '<a href="https://www.gov.uk/ok">ok</a></main>')
    assert [r["url"] for r in extract_page(html).references] == ["https://www.gov.uk/ok"]


# --- warnings and edge cases -------------------------------------------------------------------------------------------------

def test_a_page_without_main_falls_back_to_the_body_and_says_so():
    page = extract_page("<html><body><h2>Visa</h2><p>The visa needs a passport and a photo.</p></body></html>")
    assert "The visa needs a passport and a photo." in page.text and "no_main" in page.warnings


@pytest.mark.parametrize("html,warning", [
    ("<main><p>Plain words with no heading at all, just some sentences to read here.</p></main>", "no_headings"),
    ("<main><h1>T</h1><p>Short.</p></main>", "thin_content"),
])
def test_warnings(html, warning):
    assert warning in extract_page(html).warnings


@pytest.mark.parametrize("html", ["", "   ", "<html></html>", "<main></main>", "<main><script>x()</script></main>"])
def test_an_empty_page_gives_empty_text_and_a_warning_never_a_crash(html):
    page = extract_page(html)
    assert page.text == "" and "empty" in page.warnings


def test_extraction_is_deterministic():
    assert extract_page(ANSWER_PAGE) == extract_page(ANSWER_PAGE)


def test_the_title_is_the_page_title():
    assert extract_page(ANSWER_PAGE).title == "UK Student Visa Fee and Health Surcharge: Short Answer"


# --- chunking ------------------------------------------------------------------------------------------------------------------

def _long_faq_page(n=40):
    qa = "".join(f"<div><h3>Question number {i} about studying abroad?</h3><p>{'Answer sentence about topic. ' * 30} Final point {i}.</p></div>"
                 for i in range(n))
    return f"<html><head><title>Long FAQ</title></head><body><main><h1>Long FAQ</h1><h2>Frequently Asked Questions</h2>{qa}</main></body></html>"


def test_no_chunk_boundary_separates_a_question_from_its_answer():
    page = extract_page(_long_faq_page())
    chunks = [c["content"] for c in chunk_text(page.text)]       # the project's own chunker, default size and overlap
    assert len(chunks) > 3
    for i in range(40):
        question = f"Question number {i} about studying abroad?"
        home = [c for c in chunks if question in c]
        assert home, question
        assert any("Answer sentence about topic." in c.split(question, 1)[1][:400] for c in home), f"question {i} separated from its answer"


def test_chunks_follow_the_project_chunk_conventions():
    chunks = chunk_text(extract_page(_long_faq_page()).text)
    assert all(c["token_count"] <= 700 for c in chunks)            # chunk_text's own 500-token target plus its overlap, as for every tenant
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


# --- structures found on the live pages ----------------------------------------------------------------------------------------

def test_a_question_inside_a_button_inside_a_heading_is_kept_but_icons_and_tab_buttons_are_not():
    html = ('<main><h1>Guide</h1><button>Why Study Here</button><button>All</button><h2>Frequently Asked Questions</h2>'
            '<div><h3><button aria-expanded="false"><span>Is the UK a good place?</span><span><svg><path d="M1"/></svg></span></button></h3>'
            '<div style="height:0"><p>Yes, it has globally recognised universities and a post-study work route.</p></div></div></main>')
    text = extract_page(html).text
    assert "Frequently Asked Questions › Is the UK a good place?\nYes, it has globally recognised universities" in text
    assert "Why Study Here" not in text and "All" not in text.split()


def _faq_jsonld(*pairs):
    import json
    return ('<script type="application/ld+json">' + json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]}) + "</script>")


def test_faq_answers_that_only_exist_in_the_pages_structured_data_are_read_from_it():
    html = ("<html><body><main><h1>Test Prep</h1><p>We coach for IELTS, PTE and more at our centres.</p><h2>Frequently Asked Questions</h2>"
            "<div><h3><button><span>How long is each course?</span></button></h3></div>"
            + _faq_jsonld(("How long is each course?", "It depends on your test date: typically 4 to 8 weeks."),
                          ("Is the demo class really free?", "Absolutely. No commitments.")) + "</main></body></html>")
    page = extract_page(html)
    assert "Frequently Asked Questions › How long is each course?\nIt depends on your test date: typically 4 to 8 weeks." in page.text
    assert "Frequently Asked Questions › Is the demo class really free?\nAbsolutely. No commitments." in page.text


def test_a_faq_that_is_already_in_the_visible_page_is_not_repeated_from_the_structured_data():
    html = ("<html><body><main><h1>Guide</h1><h2>Frequently Asked Questions</h2>"
            "<div><h3>Can I work while studying?</h3><p>Yes, up to twenty hours a week in term time.</p></div>"
            + _faq_jsonld(("Can I work while studying?", "Yes, up to twenty hours a week in term time.")) + "</main></body></html>")
    assert extract_page(html).text.count("Can I work while studying?") == 1


@pytest.mark.parametrize("payload", ["not json", '{"@type": "FAQPage"}', '{"@type": "FAQPage", "mainEntity": "x"}',
                                     '{"@type": "FAQPage", "mainEntity": [{"name": "q"}]}', "[1, 2]", "null"])
def test_broken_structured_data_is_ignored_not_fatal(payload):
    html = f'<main><h1>Guide</h1><p>Some real page content that is long enough to be read.</p><script type="application/ld+json">{payload}</script></main>'
    assert "Some real page content" in extract_page(html).text


def test_structured_data_answers_are_text_only():
    html = ('<main><h1>G</h1><p>Intro line for this page, long enough.</p>' + _faq_jsonld(("Q one?", "<b>Bold</b> answer <img src=x onerror=alert(1)> here <a href='https://evil.com'>link</a>."))
            + "</main>")
    text = extract_page(html).text
    assert "<" not in text and "onerror" not in text and "https://" not in text and "Bold answer here link." in text


def test_a_page_title_heading_with_no_text_of_its_own_is_still_kept():
    text = extract_page("<main><h1>Top 15 Scholarships for Nepali Students in 2026</h1><h2>Chevening</h2><p>A UK government scholarship for future leaders.</p></main>").text
    assert text.startswith("Top 15 Scholarships for Nepali Students in 2026")


def test_a_breadcrumb_before_the_title_is_not_content_but_a_real_introduction_before_it_is():
    gone = extract_page('<main><div><a>Nepal</a><a>Scholarships</a><a>Study Abroad</a></div><h1>Top 15 Scholarships</h1><p>Fully funded options for master students abroad.</p></main>').text
    assert "Nepal Scholarships Study Abroad" not in gone and gone.startswith("Top 15 Scholarships")
    kept = extract_page("<main><p>This guide explains every step of applying to a UK university from Nepal, in plain words.</p><h1>UK</h1><p>Body text of the page.</p></main>").text
    assert "This guide explains every step" in kept


def test_a_title_only_heading_is_kept_as_a_line_of_its_section():
    html = ("<main><h1>Test Prep</h1><h2>What makes us the best</h2><p>We help you succeed at every step of preparation.</p>"
            "<h3>Personalized Experience</h3><h3>Custom Study Schedules</h3><h2>Next section</h2><p>Some other text lives in here.</p></main>")
    blocks = extract_page(html).blocks
    assert "What makes us the best\nWe help you succeed at every step of preparation.\nPersonalized Experience\nCustom Study Schedules" in blocks
    assert not any(b.startswith("What makes us the best › ") for b in blocks)


def test_a_heading_that_has_sub_headings_with_text_is_not_turned_into_a_line():
    html = "<main><h1>T</h1><h2>Parent</h2><h3>Child</h3><p>Child text that belongs to the child heading.</p></main>"
    blocks = extract_page(html).blocks
    assert "Parent › Child\nChild text that belongs to the child heading." in blocks and not any(b == "Parent" for b in blocks)


# --- found by checking the real pages ----------------------------------------------------------------------------------------------

def test_a_section_the_page_renders_twice_for_mobile_and_desktop_is_kept_once():
    steps = ("<h3>{n}Choose Course &amp; University</h3><p>Pick a course and shortlist universities that suit you.</p>"
             "<h3>{n}Submit Application</h3><p>Apply with your documents and statement of purpose.</p>")
    html = ("<main><h1>UK</h1><h2>UK Student Visa Process</h2>" + steps.format(n="1 . ") + steps.format(n="") + "<h2>Next</h2><p>Other text on this page.</p></main>")
    blocks = extract_page(html).blocks
    assert sum("Pick a course and shortlist universities" in b for b in blocks) == 1
    assert sum("Apply with your documents" in b for b in blocks) == 1
    assert any(b.startswith("UK Student Visa Process › 1. Choose Course & University") for b in blocks)      # the first copy is the one kept


def test_short_repeated_answers_are_not_mistaken_for_a_duplicate_section():
    html = "<main><h1>FAQ</h1><h2>Q&A</h2><h3>Can I work?</h3><p>Yes.</p><h3>Can I switch course?</h3><p>Yes.</p></main>"
    assert sum(b.endswith("Yes.") for b in extract_page(html).blocks) == 2


def test_a_list_of_university_names_is_kept_but_flagged_for_review():
    names = "".join(f"<li>University of Place {i}</li>" for i in range(12))
    page = extract_page(f"<main><h1>Study in the UK</h1><p>An introduction long enough to be read as the first paragraph here.</p><h2>Popular UK Universities</h2><ul>{names}</ul></main>")
    assert "University of Place 3" in page.text and "university_list" in page.warnings


def test_a_short_list_under_a_universities_heading_is_not_flagged():
    page = extract_page("<main><h1>G</h1><h2>Universities</h2><p>Universities set their own entry rules, so check each one before you apply.</p></main>")
    assert "university_list" not in page.warnings


def test_bare_step_counters_are_dropped_so_the_mobile_copy_of_a_step_list_is_recognised_as_a_repeat():
    html = ("<main><h1>UK</h1><h2>UK Student Visa Process</h2>"
            "<h3>1 . Choose Course</h3><p>Select a UKVI-approved institution and the right course.</p>"
            "<h3>Choose Course</h3><p>Select a UKVI-approved institution and the right course.</p><span>02</span></main>")
    blocks = extract_page(html).blocks
    assert sum("Select a UKVI-approved institution" in b for b in blocks) == 1
    assert not any(line.strip().isdigit() for b in blocks for line in b.split("\n"))


def test_a_number_with_a_decimal_or_a_unit_is_not_a_step_counter():
    text = extract_page("<main><h1>IELTS</h1><p>6.5</p><p>30 min</p><p>Most courses ask for IELTS 6.5 overall.</p></main>").text
    assert "6.5" in text and "30 min" in text
