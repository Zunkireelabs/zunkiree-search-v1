"""The gated pilot command: plan, preflight, execute. Everything here runs against fakes: a fake website, a fake store and a fake retrieval. The
command builds its real services only inside one function that no test calls, only after every refusal check has passed, and it can only
target `admizz-test`. Executing needs an approval file tied to the exact manifest and page list, and it never retires old jobs."""
import ast
import asyncio
import json
import socket
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import ingest_education_pilot as pilot
from scripts import ingest_education_sources as ing
from app.services.education_prepared_ingest import manifest_sha256
from tests.test_education_page_extractor import ANSWER_PAGE
from tests.test_education_prepared_ingest import FakeStore, TARGET
from tests.test_ingest_education_sources_script import PAGE, ROBOTS_OK, FakeClock, FakeFetcher, _html

HOST = "https://admizzeducation.com"
PILOT_IDS = ["fee", "bank", "english"]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _answer_html(pid):
    return (ANSWER_PAGE.replace("UK Student Visa Fee and Health Surcharge", f"Title {pid}").replace("Quick Answer", f"Quick Answer {pid}"))


def _url(pid):
    return f"{HOST}/answers/{pid}"


def _entry(pid, **kw):
    base = dict(id=pid, country="uk", url=_url(pid), title=f"Title {pid}", category="visa", kind="answer", sitemap_lastmod="2026-10-08",
                published="2026-10-05", checked="2026-10", verified=False, ingested_at=None)
    return {**base, **kw}


class World:
    """A fake website, a fresh manifest made by the real dry-run script from it, probe questions and an approval, all in a temp dir."""

    def __init__(self, tmp_path, pilot_ids=PILOT_IDS):
        self.dir, self.pilot_ids, self.clock = tmp_path, list(pilot_ids), FakeClock()
        pages = {f"{HOST}/robots.txt": _html(ROBOTS_OK, "text/plain")}
        for pid in self.pilot_ids:
            pages[_url(pid)] = _html(_answer_html(pid))
        pages[f"{HOST}/study-in-the-uk"] = _html(PAGE)                                    # an explanatory guide: never part of the pilot
        self.fetcher = FakeFetcher(pages, self.clock)
        reg = {"site_id": "t", "resources": [_entry(p) for p in self.pilot_ids] +
               [_entry("guide", url=f"{HOST}/study-in-the-uk", title="Study in the UK", kind="guide", category="guide", published=None, checked=None)]}
        self.registry, self.manifest_path = tmp_path / "reg.json", tmp_path / "manifest.json"
        self.registry.write_text(json.dumps(reg))
        assert ing.main(["--registry", str(self.registry), "--manifest", str(self.manifest_path)], fetcher=self.fetcher, clock=self.clock.now,
                        sleep=self.clock.sleep) == 0
        self.fetcher.calls.clear()
        self.fetcher.times.clear()                                   # the pilot run below is paced on its own
        self.manifest = json.loads(self.manifest_path.read_text())
        self.probes = tmp_path / "probes.json"
        self.probes.write_text(json.dumps({"probes": {p: [f"q1-{p}", f"q2-{p}"] for p in self.pilot_ids}}))
        self.approval = tmp_path / "approval.json"
        self.write_approval()

    def write_approval(self, **kw):
        doc = {"manifest_sha256": manifest_sha256(self.manifest), "site_id": "admizz-test", "approved_by": "Reviewer",
               "page_ids": sorted(self.pilot_ids), **kw}
        self.approval.write_text(json.dumps(doc))

    def retrieval(self, miss=()):
        async def retrieve(question):
            pid = question.split("-", 1)[1]
            return [] if pid in miss else [{"source_url": _url(pid), "source_title": "x", "content": "text"}]
        return retrieve

    def factory(self, store=None, miss=()):
        built = []
        store = store or FakeStore()

        @asynccontextmanager
        async def real_factory(site_id, *, writes):
            built.append((site_id, writes))
            yield SimpleNamespace(store=store, target=TARGET, retrieve=self.retrieval(miss))
        real_factory.built, real_factory.store = built, store
        return real_factory

    def run(self, mode, *extra, factory=None, approve=True):
        args = [mode, "--manifest", str(self.manifest_path), "--probes", str(self.probes)]
        if mode == "execute" and approve:
            args += ["--approval-file", str(self.approval)]
        return pilot.main(args + list(extra), fetcher=self.fetcher, real_factory=factory, clock=self.clock.now, sleep=self.clock.sleep, today=None)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


# --- plan: no network, no store -----------------------------------------------------------------------------------------------------------------

def test_plan_lists_only_the_source_backed_ready_pages_with_the_hash_the_approval_must_carry(world, capsys):
    factory = world.factory()
    assert world.run("plan", factory=factory) == 0
    out = capsys.readouterr().out
    for pid in PILOT_IDS:
        assert pid in out
    assert "guide" not in out.split("pilot pages")[1].split("approval")[0]                  # an explanatory guide is not in the pilot
    assert manifest_sha256(world.manifest) in out and "approved_by" in out and "estimated" in out.lower()
    assert world.fetcher.calls == [] and factory.built == []                                  # no website request, no store of any kind


def test_plan_warns_when_a_manifest_has_no_content_hashes_and_execute_refuses_it(world, capsys):
    for page in world.manifest["pages"]:
        page.pop("content_sha256", None)
    world.manifest_path.write_text(json.dumps(world.manifest))
    world.write_approval()
    assert world.run("plan") == 0 and "content hash" in capsys.readouterr().out.lower()
    factory = world.factory()
    assert world.run("execute", factory=factory) == 1
    assert "content hash" in capsys.readouterr().out.lower() and factory.built == [] and world.fetcher.calls == []


def test_plan_reports_pages_that_have_no_probe_questions(world, capsys):
    world.probes.write_text(json.dumps({"probes": {"fee": ["q1-fee", "q2-fee"]}}))
    assert world.run("plan") == 0
    assert "no probe questions" in capsys.readouterr().out


# --- execute refuses before it fetches or builds anything ----------------------------------------------------------------------------------------------

def _refused(world, capsys, needle, **kw):
    factory = world.factory()
    assert world.run("execute", factory=factory, **kw) == 1
    assert needle in capsys.readouterr().out.lower()
    assert factory.built == [] and world.fetcher.calls == [] and factory.store.jobs == {}


def test_execute_without_an_approval_file_is_refused(world, capsys):
    _refused(world, capsys, "approval", approve=False)


@pytest.mark.parametrize("change,needle", [
    ({"manifest_sha256": "0" * 64}, "different manifest"),
    ({"site_id": "dental-city"}, "dental-city"),
    ({"approved_by": " "}, "who approved"),
    ({"page_ids": ["fee"]}, "different pages"),
    ({"confirmed_retire_job_ids": ["old-job"]}, "retire"),
])
def test_an_approval_for_a_different_manifest_tenant_pages_or_with_retirement_is_refused(world, capsys, change, needle):
    world.write_approval(**change)
    _refused(world, capsys, needle)


@pytest.mark.parametrize("content", ["not json", "[]", '{"approved_by": "x"}', '{"manifest_sha256": 1, "site_id": "admizz-test", "approved_by": "x", "page_ids": "fee"}'])
def test_a_malformed_approval_file_is_refused(world, capsys, content):
    world.approval.write_text(content)
    _refused(world, capsys, "approval")


def test_only_admizz_test_can_be_targeted(world, capsys):
    factory = world.factory()
    assert world.run("execute", "--site", "dental-city", factory=factory) == 1
    assert "dental-city" in capsys.readouterr().out and factory.built == [] and world.fetcher.calls == []


def test_a_review_or_unknown_page_cannot_be_selected(world, capsys):
    factory = world.factory()
    assert world.run("execute", "--only", "guide", factory=factory) == 1
    assert world.run("execute", "--only", "nope", factory=factory) == 1
    assert factory.built == [] and world.fetcher.calls == []


def test_a_missing_probe_question_set_refuses_execution_before_any_write(world, capsys):
    world.probes.write_text(json.dumps({"probes": {"fee": ["q1-fee", "q2-fee"]}}))
    _refused(world, capsys, "no probe questions")


def test_a_manifest_that_is_not_a_manifest_is_refused(world, tmp_path, capsys):
    world.manifest_path.write_text("nope")
    _refused(world, capsys, "manifest")


# --- preflight: reads only ------------------------------------------------------------------------------------------------------------------------------

def test_preflight_fetches_prepares_and_reads_the_store_but_writes_nothing(world, capsys):
    factory = world.factory(store=FakeStore(forbid_writes=True))
    assert world.run("preflight", factory=factory) == 0
    out = capsys.readouterr().out
    assert factory.built == [("admizz-test", False)]                                          # a store opened WITHOUT writes
    assert out.count("would_add") == 3 and factory.store.jobs == {}
    assert world.fetcher.calls and all(c.startswith(HOST) for c in world.fetcher.calls)


def test_preflight_shows_what_already_exists_without_touching_it(world, capsys):
    world.run("execute", factory=(first := world.factory()))
    capsys.readouterr()
    assert world.run("preflight", factory=world.factory(store=first.store)) == 0
    assert capsys.readouterr().out.count("would_skip_already_ingested") == 3


# --- execute: the whole path against fakes ---------------------------------------------------------------------------------------------------------------

def test_execute_writes_verifies_checks_retrieval_and_reports(world, capsys, tmp_path):
    factory = world.factory()
    report = tmp_path / "report.json"
    assert world.run("execute", "--report", str(report), factory=factory) == 0
    out = capsys.readouterr().out
    assert factory.built == [("admizz-test", True)] and len(factory.store.jobs) == 3
    assert {j["url"] for j in factory.store.jobs.values()} == {_url(p) for p in PILOT_IDS}
    assert out.count("added") >= 3 and out.count("found") >= 6                                # every probe question found its page
    doc = json.loads(report.read_text())
    assert doc["ingestion"]["status"] == "completed" and all(p["action"] == "added" for p in doc["ingestion"]["pages"])
    assert all(c["passed"] for c in doc["retrieval"]) and "text" not in json.dumps(doc["ingestion"])      # no page text in the report


def test_running_execute_twice_adds_nothing_the_second_time(world, capsys):
    factory = world.factory()
    assert world.run("execute", factory=factory) == 0
    before = dict(factory.store.jobs)
    assert world.run("execute", factory=factory) == 0
    assert factory.store.jobs == before and "skipped_already_ingested" in capsys.readouterr().out


def test_execute_never_retires_or_deletes_anything(world):
    factory = world.factory()
    factory.store.seed_job("old-thin-guide", f"{HOST}/other-old", title="old", rows=1)
    assert world.run("execute", factory=factory) == 0
    assert "old-thin-guide" in factory.store.jobs
    assert not [e for e in factory.store.log if e[0] in ("delete_vectors", "delete_job")]


def test_a_store_failure_stops_the_run_cleans_up_and_skips_the_retrieval_check(world, capsys):
    factory = world.factory(store=FakeStore(fail_vectors_for={"bank"}))
    assert world.run("execute", factory=factory) == 3
    out = capsys.readouterr().out
    assert "stopped" in out and "failed" in out and "retrieval" not in out.lower().split("stopped")[1][:400]
    assert len(factory.store.jobs) == 1 and all(j["status"] == "completed" for j in factory.store.jobs.values())     # the half-written page is gone


def test_when_retrieval_does_not_find_a_page_the_run_says_so_and_still_deletes_nothing(world, capsys):
    factory = world.factory(miss={"english"})
    assert world.run("execute", factory=factory) == 4
    out = capsys.readouterr().out
    assert "english" in out and "not found" in out.lower() and len(factory.store.jobs) == 3
    assert "retire" in out.lower()                                                              # says clearly that nothing may be retired yet


def test_a_page_that_changed_on_the_website_since_the_manifest_is_refused_and_nothing_is_written(world, capsys):
    world.fetcher.pages[_url("fee")] = _html(_answer_html("fee").replace("Quick Answer fee", "Quick Answer fee, changed today"))
    factory = world.factory()
    assert world.run("execute", factory=factory) == 2
    assert "changed since the manifest" in capsys.readouterr().out and factory.store.jobs == {} and factory.store.log == []


def test_a_page_whose_canonical_url_moved_is_refused(world, capsys):
    moved = _answer_html("fee").replace("<head>", '<head><link rel="canonical" href="https://admizzeducation.com/answers/somewhere-else">')
    world.fetcher.pages[_url("fee")] = _html(moved)
    factory = world.factory()
    assert world.run("execute", factory=factory) == 1
    assert "canonical" in capsys.readouterr().out.lower() and factory.store.jobs == {}


def test_a_page_that_cannot_be_fetched_stops_everything_before_any_write(world, capsys):
    world.fetcher.pages[_url("bank")] = _html("<html></html>", ctype="application/pdf")
    factory = world.factory()
    assert world.run("execute", factory=factory) == 1
    assert "bank" in capsys.readouterr().out and factory.built == [] and factory.store.jobs == {}          # refused before the store was even built


def test_robots_txt_denial_stops_the_run(world, capsys):
    world.fetcher.pages[f"{HOST}/robots.txt"] = _html("User-agent: *\nDisallow: /answers/\n", "text/plain")
    factory = world.factory()
    assert world.run("execute", factory=factory) == 1
    assert "robots" in capsys.readouterr().out.lower() and factory.built == []


def test_requests_to_the_website_are_paced_and_stay_on_the_approved_host(world):
    world.run("execute", factory=world.factory())
    times = world.fetcher.times
    assert all(b - a >= ing.MIN_INTERVAL for a, b in zip(times, times[1:])) and all(c.startswith(HOST) for c in world.fetcher.calls)


# --- nothing real can be reached by importing or by testing ---------------------------------------------------------------------------------------------

def test_real_services_are_only_imported_inside_the_one_function_no_test_calls():
    tree = ast.parse(Path(pilot.__file__).read_text())
    top_level = {a.name for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    top_modules = {n.module for n in tree.body if isinstance(n, ast.ImportFrom) and n.module}
    forbidden = ("app.database", "app.services.ingestion", "app.services.vector_store", "app.services.query", "openai", "pinecone", "sqlalchemy")
    assert not [m for m in top_modules if m.startswith(forbidden)], top_modules
    assert not ({"async_session_maker", "IngestionService", "get_vector_store_service", "get_query_service", "SqlPineconeStore"} & top_level - {"SqlPineconeStore"})
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "real_services")
    inside = {n.module for n in ast.walk(fn) if isinstance(n, ast.ImportFrom) and n.module}
    assert {"app.database", "app.services.ingestion", "app.services.vector_store"} <= inside


def test_without_an_injected_factory_a_refused_run_still_builds_nothing(world, capsys, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("real services must not be built")
    monkeypatch.setattr(pilot, "real_services", boom)
    world.write_approval(manifest_sha256="0" * 64)
    assert pilot.main(["execute", "--manifest", str(world.manifest_path), "--probes", str(world.probes), "--approval-file", str(world.approval)],
                      fetcher=world.fetcher, clock=world.clock.now, sleep=world.clock.sleep) == 1


def test_the_old_write_flag_of_the_dry_run_script_still_refuses_and_points_here(capsys):
    assert ing.main(["--write"]) == 2
    assert "ingest_education_pilot" in capsys.readouterr().out


def test_no_command_other_than_the_pilot_imports_the_store():
    root = Path(__file__).resolve().parent.parent
    importers = []
    for path in list((root / "app").rglob("*.py")) + list((root / "scripts").rglob("*.py")):
        if path.name == "education_prepared_store.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            mods = [node.module] if isinstance(node, ast.ImportFrom) and node.module else [a.name for a in node.names] if isinstance(node, ast.Import) else []
            if any("education_prepared_store" in (m or "") for m in mods):
                importers.append(path.name)
    assert importers == ["ingest_education_pilot.py"]


# --- rollback: undo exactly what one run added -------------------------------------------------------------------------------------------------------------

def _executed(world, tmp_path, factory=None):
    factory = factory or world.factory()
    report = tmp_path / "run-report.json"
    assert world.run("execute", "--report", str(report), factory=factory) == 0
    return factory, report, json.loads(report.read_text())


def _rollback_approval(tmp_path, report_doc, job_ids, **kw):
    pages = [p["page_id"] for p in report_doc["ingestion"]["pages"] if p["job_id"] in job_ids]
    doc = {"manifest_sha256": report_doc["manifest_sha256"], "site_id": "admizz-test", "approved_by": "Reviewer", "page_ids": sorted(pages),
           "confirmed_retire_job_ids": list(job_ids), **kw}
    path = tmp_path / "rollback-approval.json"
    path.write_text(json.dumps(doc))
    return path


def _rollback(world, report, approval, factory):
    return pilot.main(["rollback", "--report", str(report), "--approval-file", str(approval)], fetcher=world.fetcher, real_factory=factory,
                      clock=world.clock.now, sleep=world.clock.sleep, today=None)


def test_the_execute_report_records_what_a_rollback_needs_and_no_page_text(world, tmp_path):
    _, _, doc = _executed(world, tmp_path)
    assert doc["manifest_sha256"] == manifest_sha256(world.manifest) and doc["site_id"] == "admizz-test"
    assert all(p["job_id"] and p["canonical_url"] and p["chunks"] >= 1 for p in doc["ingestion"]["pages"])


def test_rollback_removes_exactly_the_confirmed_jobs_of_that_run_and_nothing_else(world, tmp_path, capsys):
    factory, report, doc = _executed(world, tmp_path)
    factory.store.seed_job("unrelated-job", f"{HOST}/unrelated", rows=2)
    fee = next(p for p in doc["ingestion"]["pages"] if p["page_id"] == "fee")
    factory.store.log.clear()
    assert _rollback(world, report, _rollback_approval(tmp_path, doc, [fee["job_id"]]), world.factory(store=factory.store)) == 0
    assert fee["job_id"] not in factory.store.jobs and "unrelated-job" in factory.store.jobs and len(factory.store.jobs) == 3   # bank, english, unrelated
    assert [e for e in factory.store.log if e == ("cleanup_job",)] == [("cleanup_job",)]                                         # one job, no more
    assert "removed" in capsys.readouterr().out


@pytest.mark.parametrize("make", [
    lambda doc, tmp: {"confirmed_retire_job_ids": []},                                             # nothing confirmed
    lambda doc, tmp: {"confirmed_retire_job_ids": ["not-a-job-of-this-run"]},                       # an id this run never added
    lambda doc, tmp: {"manifest_sha256": "0" * 64},                                                # an approval for another run
    lambda doc, tmp: {"site_id": "dental-city"},
    lambda doc, tmp: {"approved_by": " "},
])
def test_rollback_refuses_an_unsafe_approval_before_anything_is_built(world, tmp_path, capsys, make):
    factory, report, doc = _executed(world, tmp_path)
    ids = [doc["ingestion"]["pages"][0]["job_id"]]
    approval = _rollback_approval(tmp_path, doc, ids, **make(doc, tmp_path))
    fresh = world.factory(store=factory.store)
    jobs_before = dict(factory.store.jobs)
    assert _rollback(world, report, approval, fresh) == 1
    assert fresh.built == [] and factory.store.jobs == jobs_before and "refused" in capsys.readouterr().out


def test_rollback_will_not_remove_a_page_that_a_run_only_skipped_because_it_already_existed(world, tmp_path, capsys):
    factory, _, first = _executed(world, tmp_path)
    second_report = tmp_path / "second.json"
    assert world.run("execute", "--report", str(second_report), factory=factory) == 0            # every page skipped: nothing was added by run 2
    doc = json.loads(second_report.read_text())
    assert {p["action"] for p in doc["ingestion"]["pages"]} == {"skipped_already_ingested"}
    approval = _rollback_approval(tmp_path, doc, [first["ingestion"]["pages"][0]["job_id"]])
    assert _rollback(world, second_report, approval, world.factory(store=factory.store)) == 1
    assert len(factory.store.jobs) == 3


def test_rollback_without_an_approval_or_with_a_bad_report_is_refused(world, tmp_path, capsys):
    factory, report, doc = _executed(world, tmp_path)
    fresh = world.factory(store=factory.store)
    assert pilot.main(["rollback", "--report", str(report)], real_factory=fresh) == 1
    bad = tmp_path / "bad.json"
    bad.write_text("nope")
    assert pilot.main(["rollback", "--report", str(bad), "--approval-file", str(_rollback_approval(tmp_path, doc, ["x"]))], real_factory=fresh) == 1
    assert fresh.built == [] and len(factory.store.jobs) == 3


def test_rolling_back_twice_is_harmless(world, tmp_path, capsys):
    factory, report, doc = _executed(world, tmp_path)
    ids = [p["job_id"] for p in doc["ingestion"]["pages"]]
    approval = _rollback_approval(tmp_path, doc, ids)
    assert _rollback(world, report, approval, world.factory(store=factory.store)) == 0 and factory.store.jobs == {}
    factory.store.log.clear()
    assert _rollback(world, report, approval, world.factory(store=factory.store)) == 0
    assert "already removed" in capsys.readouterr().out and not [e for e in factory.store.log if e[0] in ("cleanup_job", "delete_job", "delete_vectors")]


def test_a_failure_during_rollback_stops_and_leaves_the_rest_alone(world, tmp_path, capsys):
    factory, report, doc = _executed(world, tmp_path)
    ids = [p["job_id"] for p in doc["ingestion"]["pages"]]

    class Failing(FakeStore):
        async def cleanup_job(self, job_id):
            if job_id == ids[0]:
                raise RuntimeError("database unavailable")
            await super().cleanup_job(job_id)
    failing = Failing()
    failing.jobs = dict(factory.store.jobs)
    assert _rollback(world, report, _rollback_approval(tmp_path, doc, ids), world.factory(store=failing)) == 3
    assert set(failing.jobs) == set(ids) and "database unavailable" in capsys.readouterr().out          # stopped at the first failure, nothing else touched


def test_rollback_opens_the_store_with_writes_and_only_for_admizz_test(world, tmp_path):
    factory, report, doc = _executed(world, tmp_path)
    fresh = world.factory(store=factory.store)
    assert _rollback(world, report, _rollback_approval(tmp_path, doc, [doc["ingestion"]["pages"][0]["job_id"]]), fresh) == 0
    assert fresh.built == [("admizz-test", True)]
