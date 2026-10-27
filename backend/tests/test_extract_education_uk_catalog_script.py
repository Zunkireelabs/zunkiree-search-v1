"""The UK catalog dry run reaches only the approved host, obeys robots.txt, never writes inside the live catalog folder, and reports
what it read. No network: a fake fetcher serves the pages."""
import json

from app.services.education_catalog import CATALOG_DIR
from scripts import extract_education_uk_catalog as ext
from scripts.ingest_education_sources import Fetched, Pacer
from tests.test_education_university_extractor import _card, _page

HOST = "https://admizzeducation.com"
ROBOTS_OK = "User-agent: *\nAllow: /\n"


def _index(slugs, stated=None):
    links = "".join(f'<a href="/explore-universities/uk/{s}">{s}</a>' for s in slugs)
    return f"<html><body><h2>{stated if stated is not None else len(slugs)} universities</h2>{links}</body></html>"


class Fake:
    def __init__(self, pages, robots=ROBOTS_OK):
        self.pages, self.robots, self.calls = pages, robots, []

    def fetch(self, url):
        self.calls.append(url)
        if url == f"{HOST}/robots.txt":
            return Fetched(200, {"content-type": "text/plain"}, self.robots.encode())
        body = self.pages.get(url)
        if body is None:
            return Fetched(404, {"content-type": "text/html"}, b"")
        return Fetched(200, {"content-type": "text/html; charset=utf-8"}, body.encode())


def _pacer():
    return Pacer(clock=lambda: 0.0, sleep=lambda s: None)


def _site(slugs=("a-uni", "b-uni")):
    pages = {f"{HOST}/explore-universities/uk": _index(slugs)}
    for s in slugs:
        pages[f"{HOST}/explore-universities/uk/{s}"] = _page(cards_pg=_card("MSc X", "1 year", "£14,000", "total"))
    return pages


def test_reads_every_linked_university():
    fake = Fake(_site())
    result = ext.run(fake, pacer=_pacer())
    assert result.stated == 2 and result.discovered == ["a-uni", "b-uni"]
    assert [p.university.id for p in result.parsed] == ["a-uni", "b-uni"] and not result.failed and not result.problems
    assert all(u.startswith(HOST) for u in fake.calls)
    assert "DRY RUN" in result.render() and "courses read: 2" in result.render()


def test_finds_links_inside_embedded_script_data_too():
    html = ('<html><body><h2>3 universities</h2><a href="/explore-universities/uk/a-uni">a</a>'
            '<script>self.__next_f.push([1,"{\\"href\\":\\"/explore-universities/uk/b-uni\\",\\"x\\":\\"/explore-universities/uk/c-uni#course-x-1\\"}"])</script>'
            '<a href="/explore-universities/uk/a-uni">again</a><a href="/explore-universities/us/other-uni">us</a></body></html>')
    slugs, stated = ext.discover(html)
    assert slugs == ["a-uni", "b-uni", "c-uni"] and stated == 3


def test_stated_count_mismatch_is_a_problem():
    pages = _site()
    pages[f"{HOST}/explore-universities/uk"] = _index(["a-uni", "b-uni"], stated=61)
    result = ext.run(Fake(pages), pacer=_pacer())
    assert any("61 universities but 2 links" in p for p in result.problems)


def test_failed_page_is_reported_not_hidden():
    pages = _site()
    del pages[f"{HOST}/explore-universities/uk/b-uni"]
    result = ext.run(Fake(pages), pacer=_pacer())
    assert result.failed == {"b-uni": "http_404"} and len(result.parsed) == 1


def test_robots_disallow_stops_the_fetch():
    fake = Fake(_site(), robots="User-agent: *\nDisallow: /explore-universities\n")
    result = ext.run(fake, pacer=_pacer())
    assert result.problems and not result.parsed
    assert not any("/explore-universities" in u for u in fake.calls)


def test_only_and_limit():
    result = ext.run(Fake(_site(("a-uni", "b-uni", "c-uni"))), pacer=_pacer(), only=["b-uni", "c-uni"], limit=1)
    assert [p.university.id for p in result.parsed] == ["b-uni"]


def test_out_file_is_unverified_and_never_in_the_live_catalog_folder(tmp_path, capsys):
    out = tmp_path / "uk.json"
    assert ext.main(["--out", str(out)], fetcher=Fake(_site()), clock=lambda: 0.0, sleep=lambda s: None) == 0
    data = json.loads(out.read_text())
    assert data["status"] == "unverified" and data["currency"] == "GBP" and len(data["universities"]) == 2 and len(data["courses"]) == 2
    assert ext.main(["--out", str(CATALOG_DIR / "x.json")], fetcher=Fake(_site())) == 1
    assert not (CATALOG_DIR / "x.json").exists()


def test_fragment_is_written_only_when_named_right_and_every_page_was_read(tmp_path):
    ok = tmp_path / "admizz-test.uk.json"
    assert ext.main(["--fragment", str(ok)], fetcher=Fake(_site()), clock=lambda: 0.0, sleep=lambda s: None) == 0
    data = json.loads(ok.read_text())
    assert data["status"] == "unverified" and len(data["universities"]) == 2 and len(data["courses"]) == 2
    assert ext.main(["--fragment", str(tmp_path / "other.json")], fetcher=Fake(_site())) == 1
    pages = _site()
    del pages[f"{HOST}/explore-universities/uk/b-uni"]
    bad = tmp_path / "x.uk.json"
    assert ext.main(["--fragment", str(bad)], fetcher=Fake(pages), clock=lambda: 0.0, sleep=lambda s: None) == 1
    assert not bad.exists()
