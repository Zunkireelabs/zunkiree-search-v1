"""After an approved ingestion, 'it is stored' is not enough: the chatbot must actually FIND the new content for realistic questions. The
check puts each probe question (questions only, never answers) to the retrieval and passes a page when that page's own canonical url is
among the top results. It cannot judge whether the text is useful; a person still reads the answers. Retrieval is injected, so these tests
use a fake and make no call to any search service."""
import hashlib
import json

import pytest

from app.services.education_prepared_ingest import PreparedPage
from app.services.education_retrieval_check import (
    ProbeResult, load_probes, make_retrieval_check, check_page, pilot_probe_problems,
)
from app.services.education_sources import SOURCES_DIR

HOST = "https://admizzeducation.com"


def _page(pid="uk-visa-fee", path="answers/uk-student-visa-fee-nepal"):
    url = f"{HOST}/{path}"
    return PreparedPage(id=pid, canonical_url=url, title="T", chunks=[{"content": "c", "chunk_index": 0, "token_count": 1, "source_url": url, "source_title": "T"}],
                        content_sha256=hashlib.sha256(pid.encode()).hexdigest(), tokens=1)


def _retriever(table):
    """A fake retrieval: question -> list of source urls (in rank order); records every question asked."""
    asked = []

    async def retrieve(question):
        asked.append(question)
        return [{"source_url": u, "source_title": "x", "content": "text"} for u in table.get(question, [])]
    retrieve.asked = asked
    return retrieve


# --- loading the probe questions -----------------------------------------------------------------------------------------------------------------

def test_the_shipped_probes_cover_every_pilot_page_with_questions_only():
    probes = load_probes(SOURCES_DIR / "admizz-test.probes.json")
    assert set(probes) == {"uk-visa-fee", "uk-visa-bank-balance", "uk-visa-english", "uk-visa-processing", "uk-tb-test",
                           "us-visa-interview", "au-cost", "ca-visa-pal", "ca-cost",
                           "uk-cost", "uk-scholarships", "uk-gpa", "uk-intakes", "ca-permit-cap", "de-blocked-account", "de-cost",
                           "de-blocked-account-guide", "ielts-vs-pte", "scholarships-top-15", "visa-documents"}
    assert all(2 <= len(qs) <= 5 for qs in probes.values())
    assert all(q.strip() and len(q) <= 200 for qs in probes.values() for q in qs)
    # questions, not statements of fact: no figure or currency is baked into a probe
    import re
    assert not [q for qs in probes.values() for q in qs if re.search(r"[£$€₹]|\d{3,}", q)]


def test_the_probes_cover_the_pilot_pages_of_the_real_manifest():
    from datetime import date
    from app.services.education_page_dispositions import READY, dispositions_for, load_manifest
    manifest = load_manifest(SOURCES_DIR / "admizz-test.manifest.json")
    classes = {p["id"]: p["content_class"] for p in manifest["pages"]}
    pilot = {d.page_id for d in dispositions_for(manifest, today=date(2026, 10, 14)) if d.status == READY and classes[d.page_id] == "source_backed"}
    assert pilot <= set(load_probes(SOURCES_DIR / "admizz-test.probes.json"))        # every source-backed page has probes (dated ones may too)


@pytest.mark.parametrize("doc", ["not json", "[]", {"probes": "x"}, {"probes": {"a": "question"}}, {"probes": {"a": []}},
                                 {"probes": {"a": ["ok", ""]}}, {"probes": {"a": ["x" * 201]}}, {"probes": {"a": ["q"] * 6}}, {"probes": {"a": [1, 2]}},
                                 {"probes": {"A B": ["q1", "q2"]}}])
def test_a_bad_probe_file_is_refused(tmp_path, doc):
    path = tmp_path / "p.json"
    path.write_text(doc if isinstance(doc, str) else json.dumps(doc))
    with pytest.raises(ValueError):
        load_probes(path)


def test_pages_without_probes_are_reported_before_any_search_is_made():
    pages = [_page("a", "a"), _page("b", "b")]
    assert pilot_probe_problems(pages, {"a": ["q1", "q2"]}) == ["b: no probe questions, so retrieval cannot be checked"]
    assert pilot_probe_problems(pages, {"a": ["q1", "q2"], "b": ["q3", "q4"]}) == []


# --- the check -----------------------------------------------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_page_passes_when_its_own_url_is_among_the_top_results_for_every_question():
    page = _page()
    retrieve = _retriever({"q1": [f"{HOST}/other", page.canonical_url], "q2": [page.canonical_url]})
    result = await check_page(retrieve, page, ["q1", "q2"], top_n=3)
    assert result.passed and [(r.question, r.found, r.rank) for r in result.results] == [("q1", True, 2), ("q2", True, 1)]
    assert retrieve.asked == ["q1", "q2"]


@pytest.mark.asyncio
async def test_a_page_fails_when_any_question_does_not_find_it_in_the_top_n():
    page = _page()
    retrieve = _retriever({"q1": [page.canonical_url], "q2": [f"{HOST}/a", f"{HOST}/b", f"{HOST}/c", page.canonical_url]})
    result = await check_page(retrieve, page, ["q1", "q2"], top_n=3)
    assert not result.passed and [r.found for r in result.results] == [True, False]
    assert result.results[1].top_sources == [f"{HOST}/a", f"{HOST}/b", f"{HOST}/c"]      # what was found instead, for a person to read


@pytest.mark.asyncio
@pytest.mark.parametrize("returned", [[], [f"{HOST}/study-in-the-uk"], [HOST + "/answers/uk-student-visa-fee-nepal/"], ["https://evil.com/answers/uk-student-visa-fee-nepal"]])
async def test_only_the_exact_canonical_url_counts_as_found(returned):
    page = _page()
    assert not (await check_page(_retriever({"q": returned}), page, ["q"], top_n=3)).passed


@pytest.mark.asyncio
async def test_a_chunk_with_no_source_url_never_counts():
    async def retrieve(question):
        return [{"content": "text without a url"}, {"source_url": None}, {"source_url": ""}]
    assert not (await check_page(retrieve, _page(), ["q"], top_n=3)).passed


@pytest.mark.asyncio
async def test_a_failing_search_fails_the_page_it_never_raises_and_never_passes_by_accident():
    async def broken(question):
        raise RuntimeError("search is down")
    result = await check_page(broken, _page(), ["q1", "q2"], top_n=3)
    assert not result.passed and all(r.error and not r.found for r in result.results)


@pytest.mark.asyncio
async def test_a_page_with_no_questions_cannot_pass():
    assert not (await check_page(_retriever({}), _page(), [], top_n=3)).passed


@pytest.mark.asyncio
async def test_the_retirement_hook_passes_only_for_pages_whose_checks_pass_and_remembers_the_details():
    ok, bad = _page("ok", "ok"), _page("bad", "bad")
    retrieve = _retriever({"q-ok": [ok.canonical_url], "q-bad": []})
    hook = make_retrieval_check(retrieve, {"ok": ["q-ok"], "bad": ["q-bad"]}, top_n=3)
    assert await hook(ok) is True and await hook(bad) is False
    assert {c.page_id: c.passed for c in hook.checks} == {"ok": True, "bad": False}
    assert await make_retrieval_check(retrieve, {}, top_n=3)(ok) is False       # no probes: not checked, so not passed
