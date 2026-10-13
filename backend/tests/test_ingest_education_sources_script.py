"""The dry-run ingestion script fetches the registry's pages politely and reports what a real ingestion WOULD store. It never
writes anywhere (no database, no vector store, no embeddings call, no registry rewrite), reaches only the approved host, obeys
robots.txt, and never runs without a fake fetcher in these tests (no network)."""
import json
from pathlib import Path

import httpx
import pytest

from app.services import education_sources as src
from app.services.education_sources import Resource
from scripts import ingest_education_sources as ing
from scripts.ingest_education_sources import (
    MAX_BYTES, MAX_REDIRECTS, MIN_INTERVAL, FetchError, Fetched, FetchTimeout, HttpxFetcher, Pacer, is_fresh, main,
    run_dry_run,
)

HOST = "https://admizzeducation.com"
PAGE = ("<html><head><title>Study in the UK - Admizz Education</title>"
        '<link rel="canonical" href="https://admizzeducation.com/study-in-the-uk"></head>'
        "<body><main>" + "".join(f"<p>Paragraph number {i} about studying in the UK and what students should know.</p>" for i in range(40))
        + "</main></body></html>")
ROBOTS_OK = "User-agent: *\nAllow: /\n"


def _res(rid="uk-guide", path="study-in-the-uk", **kw):
    base = dict(id=rid, country="uk", url=f"{HOST}/{path}", title="Study in the UK", category="guide", kind="guide")
    return Resource(**{**base, **kw})


def _html(body=PAGE, ctype="text/html; charset=utf-8", status=200):
    return Fetched(status=status, headers={"content-type": ctype}, body=body.encode(), location=None)


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


class FakeFetcher:
    """Serves `pages` by url; records every url asked for and the time of each request."""

    def __init__(self, pages, clock=None):
        self.pages, self.clock, self.calls, self.times = dict(pages), clock, [], []

    def fetch(self, url):
        self.calls.append(url)
        if self.clock:
            self.times.append(self.clock.now())
        page = self.pages.get(url)
        if page is None:
            return Fetched(status=404, headers={"content-type": "text/html"}, body=b"", location=None)
        if isinstance(page, Exception):
            raise page
        return page


def _run(resources, pages, robots=ROBOTS_OK):
    clock = FakeClock()
    fetcher = FakeFetcher({f"{HOST}/robots.txt": _html(robots, "text/plain"), **pages}, clock)
    report = run_dry_run(resources, fetcher, pacer=Pacer(clock=clock.now, sleep=clock.sleep))
    return report, fetcher, clock


# --- what it reports ---------------------------------------------------------------------------------------------------

def test_a_fetched_page_is_chunked_and_reported_with_its_canonical_url_and_title():
    report, fetcher, _ = _run([_res()], {f"{HOST}/study-in-the-uk": _html()})
    assert report.fetched == 1 and report.chunked_pages == 1 and report.total_chunks >= 1 and not report.rejected
    [item] = report.eligible
    assert item["id"] == "uk-guide" and item["canonical_url"] == f"{HOST}/study-in-the-uk"
    assert item["title"] == "Study in the UK - Admizz Education" and item["chunks"] == report.total_chunks
    assert fetcher.calls == [f"{HOST}/robots.txt", f"{HOST}/study-in-the-uk"]


def test_a_canonical_link_to_another_host_is_ignored():
    page = PAGE.replace('href="https://admizzeducation.com/study-in-the-uk"', 'href="https://evil.com/steal"')
    report, _, _ = _run([_res()], {f"{HOST}/study-in-the-uk": _html(page)})
    assert report.eligible[0]["canonical_url"] == f"{HOST}/study-in-the-uk"        # the url we fetched, not the lie


def test_the_report_counts_everything_and_renders():
    pages = {f"{HOST}/study-in-the-uk": _html(), f"{HOST}/test-prep": _html(ctype="application/pdf")}
    report, _, _ = _run([_res(), _res("tp", "test-prep"), _res("old", "old", ingested_at="2026-10-10", sitemap_lastmod="2026-10-08")], pages)
    assert (report.fetched, report.skipped, report.rejected) == (2, 1, {"content_type": 1})
    text = report.render()
    for needle in ("fetched: 2", "skipped (fresh): 1", "rejected: 1", "content_type", "eligible for ingestion: 1", "DRY RUN"):
        assert needle in text


# --- robots, redirects, content, size, timeouts, errors -----------------------------------------------------------------

def test_robots_txt_denial_means_the_page_is_never_fetched():
    report, fetcher, _ = _run([_res("a", "answers/x"), _res("g")], {f"{HOST}/answers/x": _html(), f"{HOST}/study-in-the-uk": _html()},
                              robots="User-agent: *\nDisallow: /answers/\n")
    assert report.rejected == {"robots": 1} and report.fetched == 1
    assert f"{HOST}/answers/x" not in fetcher.calls


def test_a_robots_txt_that_cannot_be_read_stops_everything():
    report, fetcher, _ = _run([_res()], {f"{HOST}/robots.txt": _html("oops", "text/plain", status=503), f"{HOST}/study-in-the-uk": _html()})
    assert report.rejected == {"robots_unavailable": 1} and fetcher.calls == [f"{HOST}/robots.txt"]


def test_a_missing_robots_txt_means_no_restrictions():
    report, _, _ = _run([_res()], {f"{HOST}/robots.txt": _html("", "text/plain", status=404), f"{HOST}/study-in-the-uk": _html()})
    assert report.fetched == 1


def _redirect(to, status=301):
    return Fetched(status=status, headers={"content-type": "text/html"}, body=b"", location=to)


def test_a_redirect_within_the_approved_host_is_followed():
    pages = {f"{HOST}/old": _redirect("/study-in-the-uk"), f"{HOST}/study-in-the-uk": _html()}
    report, fetcher, _ = _run([_res("o", "old")], pages)
    assert report.fetched == 1 and fetcher.calls[-1] == f"{HOST}/study-in-the-uk"


@pytest.mark.parametrize("target", ["https://evil.com/x", "http://admizzeducation.com/x", "https://admizzeducation.com.evil.com/x",
                                    "https://www.admizzeducation.com/x", "javascript:alert(1)", "//evil.com/x"])
def test_a_redirect_off_the_approved_host_is_rejected_and_never_requested(target):
    report, fetcher, _ = _run([_res("o", "old")], {f"{HOST}/old": _redirect(target)})
    assert report.rejected == {"redirect_host": 1} and report.fetched == 0
    assert all(c.startswith(HOST) for c in fetcher.calls)


def test_a_redirect_loop_is_cut_off():
    pages = {f"{HOST}/a": _redirect("/b"), f"{HOST}/b": _redirect("/a")}
    report, fetcher, _ = _run([_res("a", "a")], pages)
    assert report.rejected == {"too_many_redirects": 1} and len(fetcher.calls) <= MAX_REDIRECTS + 2


def test_only_html_is_accepted():
    for ctype in ("application/pdf", "application/json", "image/png", "text/plain", ""):
        report, _, _ = _run([_res()], {f"{HOST}/study-in-the-uk": _html(ctype=ctype)})
        assert report.rejected == {"content_type": 1}, ctype


def test_an_oversized_page_is_rejected():
    report, _, _ = _run([_res()], {f"{HOST}/study-in-the-uk": Fetched(200, {"content-type": "text/html"}, b"x" * (MAX_BYTES + 1), None)})
    assert report.rejected == {"too_large": 1}


def test_a_timeout_or_network_error_rejects_that_page_and_the_run_continues():
    pages = {f"{HOST}/slow": FetchTimeout("slow"), f"{HOST}/down": FetchError("boom"), f"{HOST}/study-in-the-uk": _html()}
    report, _, _ = _run([_res("s", "slow"), _res("d", "down"), _res()], pages)
    assert report.rejected == {"timeout": 1, "error": 1} and report.fetched == 1


def test_http_errors_and_empty_pages_are_rejected():
    report, _, _ = _run([_res("m", "missing"), _res("e", "empty")], {f"{HOST}/empty": _html("<html><body></body></html>")})
    assert report.rejected == {"http_404": 1, "empty": 1}


def test_a_url_outside_the_approved_host_is_never_fetched_even_if_it_got_into_the_list():
    bad = Resource.model_construct(id="x", country=None, url="https://evil.com/x", title="x", category="guide", kind="guide",
                                   sitemap_lastmod=None, published=None, checked=None, verified=False, ingested_at=None)
    report, fetcher, _ = _run([bad], {})
    assert report.rejected == {"url": 1} and fetcher.calls == []             # nothing at all is requested for it


# --- pacing ------------------------------------------------------------------------------------------------------------------

def test_requests_are_at_least_one_second_apart_including_the_robots_request():
    pages = {f"{HOST}/{p}": _html() for p in ("a", "b", "c")}
    _, fetcher, _ = _run([_res(r, r) for r in ("a", "b", "c")], pages)
    gaps = [b - a for a, b in zip(fetcher.times, fetcher.times[1:])]
    assert len(gaps) == 3 and all(g >= MIN_INTERVAL for g in gaps)
    assert MIN_INTERVAL >= 1.0


def test_the_pacer_only_waits_when_it_has_to():
    clock = FakeClock()
    pacer = Pacer(clock=clock.now, sleep=clock.sleep)
    pacer.wait()                          # first request: no wait
    clock.t += 5                          # five seconds of other work
    pacer.wait()
    assert clock.sleeps == []
    clock.t += 0.25
    pacer.wait()
    assert clock.sleeps == [pytest.approx(MIN_INTERVAL - 0.25)]


# --- freshness ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("lastmod,ingested,fresh", [
    ("2026-10-08", "2026-10-09", True),
    ("2026-10-08", "2026-10-08", True),
    ("2026-10-08", "2026-10-07", False),
    ("2026-10-08", "2026-10-09T10:00:00", True),
    ("2026-10-08", None, False),          # never ingested: eligible
    (None, "2026-10-09", False),          # no lastmod: nothing to compare, so do not skip
    ("not a date", "2026-10-09", False),  # not meaningful: do not skip
    ("2026-10-08", "garbage", False),
    (None, None, False),
])
def test_freshness_is_decided_only_from_two_valid_dates(lastmod, ingested, fresh):
    assert is_fresh(lastmod, ingested) is fresh


def test_a_fresh_page_is_not_fetched_at_all():
    report, fetcher, _ = _run([_res(ingested_at="2026-10-09", sitemap_lastmod="2026-10-08")], {f"{HOST}/study-in-the-uk": _html()})
    assert report.skipped == 1 and report.fetched == 0 and fetcher.calls == []      # not even robots.txt is needed


# --- it writes nothing -------------------------------------------------------------------------------------------------------

def _registry_file(tmp_path):
    doc = {"site_id": "t", "resources": [json.loads(_res().model_dump_json())]}
    path = tmp_path / "t.json"
    path.write_text(json.dumps(doc, indent=2))
    return path


def test_a_normal_run_touches_no_database_vector_store_embeddings_or_registry(tmp_path, monkeypatch, capsys):
    from app.services import ingestion

    def boom(*a, **k):
        raise AssertionError("a dry run must not write or call an external service")
    monkeypatch.setattr(ingestion.IngestionService, "ingest_url", boom)
    monkeypatch.setattr(ingestion.IngestionService, "_process_chunks", boom)
    monkeypatch.setattr("app.database.async_session_maker", boom)
    monkeypatch.setattr("app.services.embeddings.get_embedding_service", boom, raising=False)
    path = _registry_file(tmp_path)
    before = path.read_bytes()
    clock = FakeClock()
    fetcher = FakeFetcher({f"{HOST}/robots.txt": _html(ROBOTS_OK, "text/plain"), f"{HOST}/study-in-the-uk": _html()}, clock)
    assert main(["--registry", str(path)], fetcher=fetcher, clock=clock.now, sleep=clock.sleep) == 0
    assert path.read_bytes() == before                      # ingested_at is not rewritten by a dry run
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "fetched: 1" in out


def test_write_mode_is_not_implemented_and_does_nothing(tmp_path, capsys):
    fetcher = FakeFetcher({})
    assert main(["--registry", str(_registry_file(tmp_path)), "--write"], fetcher=fetcher) == 2
    assert fetcher.calls == []
    assert "separate explicit approval" in capsys.readouterr().out


def test_the_script_imports_nothing_from_the_write_path():
    """(`app.services/__init__` loads every service for the whole app, so sys.modules cannot show this; the script's own imports do.)"""
    import ast
    tree = ast.parse(Path(ing.__file__).read_text())
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | \
               {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    forbidden = ("app.services.ingestion", "app.services.vector_store", "app.services.embeddings", "app.database", "app.models",
                 "openai", "pinecone", "sqlalchemy")
    assert not [m for m in imported if m.startswith(forbidden)], imported
    assert imported >= {"app.services.education_sources", "app.utils.chunking"}      # only the pure helpers


def test_the_only_site_it_reads_is_what_the_registry_lists(tmp_path):
    src.reset_sources()
    clock = FakeClock()
    fetcher = FakeFetcher({f"{HOST}/robots.txt": _html(ROBOTS_OK, "text/plain"), f"{HOST}/study-in-the-uk": _html()}, clock)
    main(["--registry", str(_registry_file(tmp_path))], fetcher=fetcher, clock=clock.now, sleep=clock.sleep)
    assert set(fetcher.calls) == {f"{HOST}/robots.txt", f"{HOST}/study-in-the-uk"}


# --- the real fetcher (no network: a mock transport) ----------------------------------------------------------------------------

def _fetcher(handler):
    return HttpxFetcher(transport=httpx.MockTransport(handler))


def test_the_real_fetcher_identifies_itself_and_does_not_follow_redirects():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(302, headers={"location": "https://evil.com/x"})
    got = _fetcher(handler).fetch(f"{HOST}/old")
    assert got.status == 302 and got.location == "https://evil.com/x"          # reported, never followed
    assert "ZunkireeSearch" in seen["ua"] and "github.com/Zunkireelabs/zunkiree-search-v1" in seen["ua"]


def test_the_real_fetcher_stops_reading_a_huge_body():
    got = _fetcher(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * (MAX_BYTES * 3))).fetch(f"{HOST}/big")
    assert len(got.body) == MAX_BYTES + 1                                        # one byte over the limit is enough to reject it


def test_the_real_fetcher_maps_a_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)
    with pytest.raises(FetchTimeout):
        _fetcher(handler).fetch(f"{HOST}/slow")


def test_the_real_fetcher_maps_a_network_error():
    def handler(request):
        raise httpx.ConnectError("down", request=request)
    with pytest.raises(FetchError):
        _fetcher(handler).fetch(f"{HOST}/down")


def test_the_real_fetcher_refuses_an_unapproved_url_before_any_request():
    called = []
    with pytest.raises(FetchError):
        _fetcher(lambda r: called.append(r) or httpx.Response(200)).fetch("https://evil.com/x")
    assert called == []


# --- the manifest ---------------------------------------------------------------------------------------------------------------

from tests.test_education_page_extractor import ANSWER_PAGE   # noqa: E402  (a page shaped like the live answer pages)
from app.services.education_ingest_plan import ExistingSource  # noqa: E402


def _html_at(path):
    """The sample page, declaring `path` as its own canonical url (the shared PAGE fixture declares /study-in-the-uk)."""
    return _html(PAGE.replace('href="https://admizzeducation.com/study-in-the-uk"', f'href="{HOST}/{path}"'))


def _run_with(resources, pages, existing=None):
    clock = FakeClock()
    fetcher = FakeFetcher({f"{HOST}/robots.txt": _html(ROBOTS_OK, "text/plain"), **pages}, clock)
    return run_dry_run(resources, fetcher, pacer=Pacer(clock=clock.now, sleep=clock.sleep), existing=existing)


def test_every_registry_page_gets_a_manifest_entry_whatever_happened_to_it():
    resources = [_res(), _res("bad", "bad"), _res("old", "old", ingested_at="2026-10-10", sitemap_lastmod="2026-10-08")]
    report = _run_with(resources, {f"{HOST}/study-in-the-uk": _html(), f"{HOST}/bad": _html(ctype="application/pdf")})
    by_id = {e["id"]: e for e in report.manifest}
    assert set(by_id) == {"uk-guide", "bad", "old"}
    assert (by_id["uk-guide"]["eligible"], by_id["bad"]["eligible"], by_id["old"]["eligible"]) == (True, False, False)
    assert by_id["bad"]["reason"] == "content_type" and by_id["old"]["reason"] == "fresh"
    assert by_id["uk-guide"]["registry_freshness"] == {"sitemap_lastmod": None, "published": None, "checked": None, "ingested_at": None}
    assert by_id["uk-guide"]["category"] == "guide" and by_id["uk-guide"]["country"] == "uk" and by_id["uk-guide"]["kind"] == "guide"


def test_no_manifest_entry_is_ever_marked_verified():
    report = _run_with([_res(), _res("bad", "bad")], {f"{HOST}/study-in-the-uk": _html()})
    assert report.manifest and all(e["verified"] is False for e in report.manifest)


def test_an_eligible_entry_reports_size_warnings_dropped_sections_references_and_a_class():
    report = _run_with([_res("fee", "answers/fee", kind="answer", category="visa", published="2026-10-05", checked="2026-10")],
                       {f"{HOST}/answers/fee": _html(ANSWER_PAGE)})
    [e] = report.eligible
    assert e["characters"] > 500 and e["chunks"] >= 1 and e["tokens"] > 100 and e["warnings"] == []
    assert {"Related guides", "Related Articles"} <= set(e["dropped_sections"])
    assert [r["url"] for r in e["references"]][0].startswith("https://www.gov.uk/")
    assert e["has_checked_statement"] is True and e["content_class"] == "source_backed"
    assert e["title"] == "UK Student Visa Fee and Health Surcharge: Short Answer"


def test_a_page_with_no_dates_or_sources_is_explanatory_and_empty_content_is_flagged():
    report = _run_with([_res(), _res("blank", "blank")], {f"{HOST}/study-in-the-uk": _html(), f"{HOST}/blank": _html("<html><body></body></html>")})
    assert report.eligible[0]["content_class"] == "explanatory"
    assert report.rejected == {"empty": 1}


def test_overlap_with_existing_chunks_is_reported_as_title_only_unless_the_url_matches():
    existing = [ExistingSource("j1", "text", None, "Study in the UK - Admizz Education", 1, 651, 140),
                ExistingSource("j2", "url", f"{HOST}/test-prep", "Whatever", 3, 2000, 500)]
    report = _run_with([_res(), _res("tp", "test-prep", category="test_prep", country=None, kind="service")],
                       {f"{HOST}/study-in-the-uk": _html(), f"{HOST}/test-prep": _html_at("test-prep")}, existing)
    overlaps = {e["id"]: e["overlap"] for e in report.eligible}
    assert overlaps["uk-guide"]["match"] == "title" and overlaps["uk-guide"]["proof"] == "title_only_not_proven_same_source"
    assert overlaps["tp"]["match"] == "url" and overlaps["tp"]["proof"] == "same_url"
    assert report.plan["add"] == ["uk-guide"] and [s["reason"] for s in report.plan["skip"]] == ["already_ingested_same_url"]
    assert report.plan["retire_candidates"] == [{"job_id": "j1", "page_id": "uk-guide", "proof": "title_only_not_proven_same_source"}]
    assert "MAY be replaced" in report.render() and "title match only" in report.render()


def test_the_embedding_volume_comes_from_the_manifest_and_states_its_assumptions():
    report = _run_with([_res(), _res("b", "b")], {f"{HOST}/study-in-the-uk": _html(), f"{HOST}/b": _html_at("b")})
    assert report.estimate["chunks"] == report.total_chunks and report.estimate["tokens"] == sum(e["tokens"] for e in report.eligible)
    assert report.estimate["api_calls"] == 1 and report.problems == []
    text = report.render()
    assert "embedding volume if ingested" in text and "Assumption" in text


def test_the_manifest_file_is_written_only_where_asked_and_the_registry_and_snapshot_are_untouched(tmp_path):
    registry, manifest, snapshot = _registry_file(tmp_path), tmp_path / "out" / "m.json", tmp_path / "existing.json"
    manifest.parent.mkdir()
    snapshot.write_text(json.dumps([{"job_id": "j1", "source_type": "text", "job_source_url": None, "chunk_source_url": "",
                                     "job_source_filename": "Study in the UK - Admizz Education", "source_title": "Study in the UK - Admizz Education",
                                     "chunks": 1, "chars": 651, "tokens": 140}]))
    before = (registry.read_bytes(), snapshot.read_bytes())
    clock = FakeClock()
    fetcher = FakeFetcher({f"{HOST}/robots.txt": _html(ROBOTS_OK, "text/plain"), f"{HOST}/study-in-the-uk": _html()}, clock)
    assert main(["--registry", str(registry), "--existing", str(snapshot), "--manifest", str(manifest)], fetcher=fetcher,
                clock=clock.now, sleep=clock.sleep) == 0
    assert (registry.read_bytes(), snapshot.read_bytes()) == before
    doc = json.loads(manifest.read_text())
    assert doc["dry_run"] is True and doc["existing_jobs"] == 1 and doc["pages"][0]["overlap"]["job_id"] == "j1"
    assert doc["plan"]["retire_candidates"] and doc["estimate"]["chunks"] >= 1 and "verified" in json.dumps(doc["pages"][0])
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["existing.json", "m.json", "t.json"]   # nothing else was created


@pytest.mark.parametrize("content", ["not json", '{"a": 1}', '[{"nope": 1}]'])
def test_an_unreadable_existing_snapshot_stops_the_run_before_any_request(tmp_path, content, capsys):
    snapshot = tmp_path / "existing.json"
    snapshot.write_text(content)
    fetcher = FakeFetcher({})
    assert main(["--registry", str(_registry_file(tmp_path)), "--existing", str(snapshot)], fetcher=fetcher) == 1
    assert fetcher.calls == [] and "existing-chunks snapshot" in capsys.readouterr().err


def test_two_pages_that_declare_the_same_canonical_url_are_a_preflight_problem():
    report = _run_with([_res(), _res("b", "b")], {f"{HOST}/study-in-the-uk": _html(), f"{HOST}/b": _html()})     # both say /study-in-the-uk
    assert any("duplicate canonical url" in p for p in report.problems)


def test_a_link_only_page_is_fetched_for_the_report_but_is_not_eligible_for_ingestion():
    resources = [_res(), _res("book", "register", category="contact", country=None, kind="service")]
    report = _run_with(resources, {f"{HOST}/study-in-the-uk": _html(), f"{HOST}/register": _html_at("register")})
    by_id = {e["id"]: e for e in report.manifest}
    assert by_id["uk-guide"]["eligible_for_ingestion"] is True and by_id["uk-guide"]["plan_action"] == "add"
    assert by_id["book"]["eligible_for_ingestion"] is False and by_id["book"]["plan_action"] == "skip: link_only_category"
    assert report.plan["add"] == ["uk-guide"]
    assert "eligible for ingestion: 1 " in report.render()
    assert report.estimate["chunks"] == by_id["uk-guide"]["chunks"]                  # the link-only page costs nothing


def test_the_report_names_why_each_page_is_in_or_out():
    report = _run_with([_res(), _res("bad", "bad")], {f"{HOST}/study-in-the-uk": _html(), f"{HOST}/bad": _html(ctype="application/pdf")})
    by_id = {e["id"]: e for e in report.manifest}
    assert by_id["bad"]["eligible_for_ingestion"] is False and by_id["bad"]["plan_action"] == "skip: content_type"


# --- content hashes and dispositions in the manifest ----------------------------------------------------------------------------------

def test_every_eligible_manifest_entry_records_the_hash_of_its_extracted_text():
    import hashlib
    from app.services.education_page_extractor import extract_page
    report = _run_with([_res()], {f"{HOST}/study-in-the-uk": _html()})
    assert report.eligible[0]["content_sha256"] == hashlib.sha256(extract_page(PAGE).text.encode()).hexdigest()
    again = _run_with([_res()], {f"{HOST}/study-in-the-uk": _html()})
    assert again.eligible[0]["content_sha256"] == report.eligible[0]["content_sha256"]               # stable for the same page
    changed = _run_with([_res()], {f"{HOST}/study-in-the-uk": _html(PAGE.replace("Paragraph number 3", "Paragraph number three"))})
    assert changed.eligible[0]["content_sha256"] != report.eligible[0]["content_sha256"]


def test_every_manifest_entry_carries_its_disposition_and_the_reasons():
    resources = [_res("fee", "answers/fee", kind="answer", category="visa", published="2026-10-05", checked="2026-10"),
                 _res("guide", "guide"), _res("bad", "bad")]
    report = _run_with(resources, {f"{HOST}/answers/fee": _html(ANSWER_PAGE), f"{HOST}/guide": _html_at("guide"), f"{HOST}/bad": _html(ctype="application/pdf")})
    by = {e["id"]: e for e in report.manifest}
    assert (by["fee"]["disposition"], by["fee"]["disposition_reasons"]) == ("ready", [])
    assert by["guide"]["disposition"] == "review" and "no_date_or_official_source" in by["guide"]["disposition_reasons"]
    assert by["bad"]["disposition"] == "excluded" and by["bad"]["disposition_reasons"] == ["content_type"]
    assert "dispositions: ready 1, review 1, excluded 1, undecided 0" in report.render()
