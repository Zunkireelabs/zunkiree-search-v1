"""The concrete store behind the prepared-pages adapter, exercised with a fake database session and fake vector and embedding clients.
Every dependency must be handed in explicitly, writes are off unless explicitly enabled, every statement is scoped to the target
customer and to exact job ids, and any attempt to open a network connection fails the test."""
import ast
import hashlib
import socket
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from app.services import education_prepared_ingest as pi
from app.services import education_prepared_store as ps
from app.services.education_ingest_plan import PageWriteError
from app.services.education_page_extractor import extract_page
from app.services.education_prepared_ingest import PreparedPage, Target, prepare_page
from app.services.education_prepared_store import SqlPineconeStore, WritesNotEnabled
from app.services.ingestion import IngestionService
from app.services.vector_store import VectorStoreService

HOST = "https://admizzeducation.com"
CUSTOMER = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
TARGET = Target("admizz-test", CUSTOMER, "admizz-test")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test tried to open a network connection")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def _page(n=2, pid="uk-visa-fee", path="answers/uk-student-visa-fee-nepal", title="UK Student Visa Fee"):
    url = f"{HOST}/{path}"
    chunks = [{"content": f"chunk {i}", "chunk_index": i, "token_count": 10, "source_url": url, "source_title": title} for i in range(n)]
    return PreparedPage(id=pid, canonical_url=url, title=title, chunks=chunks, content_sha256=hashlib.sha256(pid.encode()).hexdigest(), tokens=10 * n)


class FakeResult:
    def __init__(self, scalars=(), scalar=None, one=None):
        self._scalars, self._scalar, self._one = list(scalars), scalar, one

    def scalars(self):
        return SimpleNamespace(all=lambda: self._scalars)

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._one


class FakeDb:
    def __init__(self, results=()):
        self.results, self.statements, self.added, self.log = list(results), [], [], []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.log.append("commit")

    async def refresh(self, obj):
        pass

    async def execute(self, statement, *a, **k):
        self.statements.append(statement)
        self.log.append("execute")
        return self.results.pop(0) if self.results else FakeResult()


class FakeVectors:
    """Stands in for VectorStoreService: records what would be asked of Pinecone, holds a set of 'existing' vector ids."""

    def __init__(self, existing=(), fail_upsert=False, log=None):
        self.existing, self.fail_upsert, self.log = set(existing), fail_upsert, log if log is not None else []
        self.deleted, self.upserted = [], []

    async def existing_ids(self, ids, namespace):
        self.log.append(("existing_ids", tuple(ids), namespace))
        return {i for i in ids if i in self.existing}

    async def delete_vectors(self, ids, namespace):
        self.log.append(("delete_vectors", tuple(ids), namespace))
        self.deleted.append((tuple(ids), namespace))
        self.existing -= set(ids)

    async def upsert_vectors(self, vectors, namespace):
        self.log.append(("upsert", namespace))
        if self.fail_upsert:
            raise RuntimeError("pinecone down")
        self.upserted.extend(vectors)
        self.existing |= {v["id"] for v in vectors}


def _ingestion_service(vectors, embed_log):
    service = IngestionService.__new__(IngestionService)

    async def create_embeddings(texts):
        embed_log.append(len(texts))
        return [[0.1, 0.2] for _ in texts]
    service.embedding_service = SimpleNamespace(create_embeddings=create_embeddings)
    service.vector_store = vectors
    return service


def _store(db=None, vectors=None, writes=True, embed_log=None):
    vectors = vectors or FakeVectors()
    return SqlPineconeStore(db=db or FakeDb(), ingestion_service=_ingestion_service(vectors, embed_log if embed_log is not None else []),
                            vector_store=vectors, target=TARGET, allow_real_writes=writes), vectors


def _sql(stmt):
    return str(stmt.compile(dialect=postgresql.dialect()))


# --- nothing can fall through to a real client ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("missing", ["db", "ingestion_service", "vector_store", "target"])
def test_every_dependency_must_be_handed_in_explicitly(missing):
    args = dict(db=FakeDb(), ingestion_service=object(), vector_store=object(), target=TARGET)
    args[missing] = None
    with pytest.raises(TypeError):
        SqlPineconeStore(**args)


def test_omitting_a_dependency_is_an_error_not_a_default():
    with pytest.raises(TypeError):
        SqlPineconeStore(db=FakeDb(), target=TARGET)          # type: ignore[call-arg]
    with pytest.raises(TypeError):
        SqlPineconeStore(FakeDb(), object(), object(), TARGET)  # type: ignore[misc]  (keyword-only)


def test_writes_are_off_unless_explicitly_enabled():
    store, _ = _store(writes=False)
    assert store.writes_enabled is False
    assert _store(writes=True)[0].writes_enabled is True
    with pytest.raises(TypeError):
        SqlPineconeStore(db=FakeDb(), ingestion_service=object(), vector_store=object(), target=TARGET, allow_real_writes="yes")


@pytest.mark.asyncio
async def test_a_store_with_writes_off_refuses_every_write_and_makes_no_call():
    db, vectors = FakeDb(), FakeVectors()
    store, _ = _store(db=db, vectors=vectors, writes=False)
    for call in (store.write_page(_page()), store.cleanup_job(str(uuid.uuid4())), store.delete_vectors(["x"]), store.delete_job(str(uuid.uuid4()))):
        with pytest.raises(WritesNotEnabled):
            await call
    assert db.statements == [] and db.added == [] and vectors.log == []


def test_neither_module_imports_a_factory_a_session_maker_or_a_real_client():
    forbidden_names = {"get_ingestion_service", "get_vector_store_service", "get_embedding_service", "get_background_embedding_service",
                       "async_session_maker", "get_db", "get_settings", "Pinecone", "OpenAI", "AsyncOpenAI"}
    for module in (pi, ps):
        tree = ast.parse(Path(module.__file__).read_text())
        names = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not (names & forbidden_names), (module.__name__, names & forbidden_names)
        assert not [m for m in modules if m.startswith(("app.database", "openai", "pinecone"))], (module.__name__, modules)


def test_the_adapter_is_wired_only_to_the_one_gated_pilot_command_and_to_no_route():
    root = Path(__file__).resolve().parent.parent
    importers = []
    for path in list((root / "app").rglob("*.py")) + list((root / "scripts").rglob("*.py")):
        if path.name == "education_prepared_store.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            mods = [node.module] if isinstance(node, ast.ImportFrom) and node.module else [a.name for a in node.names] if isinstance(node, ast.Import) else []
            if any("education_prepared_store" in (m or "") for m in mods):
                importers.append(str(path.relative_to(root)))
    assert importers == ["scripts/ingest_education_pilot.py"]      # the one gated command (plan / preflight / execute); nothing under app/


def test_a_network_attempt_would_fail_this_suite():
    with pytest.raises(AssertionError):
        socket.create_connection(("example.com", 80))


# --- reads are scoped to the target customer ------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_describe_target_reads_the_customer_record():
    customer = SimpleNamespace(site_id="admizz-test", id=CUSTOMER, website_type="education")
    store, _ = _store(db=FakeDb([FakeResult(one=customer)]))
    info = await store.describe_target()
    assert (info.site_id, info.customer_id, info.website_type, info.namespace) == ("admizz-test", CUSTOMER, "education", "admizz-test")


@pytest.mark.asyncio
async def test_a_missing_customer_gives_a_target_that_cannot_validate():
    store, _ = _store(db=FakeDb([FakeResult(one=None)]))
    info = await store.describe_target()
    assert pi.validate_target(TARGET, info)


@pytest.mark.asyncio
async def test_jobs_for_a_url_come_with_row_and_vector_counts():
    job = SimpleNamespace(id=uuid.uuid4(), status="completed", source_url=f"{HOST}/x", source_filename="T", chunks_created=3)
    db = FakeDb([FakeResult(scalars=[job]), FakeResult(scalar=3)])
    vectors = FakeVectors(existing={f"{job.id}_0", f"{job.id}_1"})           # one vector missing
    store, _ = _store(db=db, vectors=vectors)
    [state] = await store.jobs_for_url(f"{HOST}/x")
    assert (state.job_id, state.status, state.chunks_expected, state.rows, state.vectors) == (str(job.id), "completed", 3, 3, 2)
    sql = _sql(db.statements[0])
    assert "ingestion_jobs.customer_id" in sql and "ingestion_jobs.source_url" in sql


@pytest.mark.asyncio
async def test_verify_counts_rows_and_vectors_in_both_stores():
    job_id = uuid.uuid4()
    db = FakeDb([FakeResult(scalar=2)])
    store, _ = _store(db=db, vectors=FakeVectors(existing={f"{job_id}_0", f"{job_id}_1"}))
    found = await store.verify_job(str(job_id), 2)
    assert (found.rows, found.vectors) == (2, 2)
    assert "document_chunks.customer_id" in _sql(db.statements[0]) and "document_chunks.job_id" in _sql(db.statements[0])


@pytest.mark.asyncio
async def test_job_vector_ids_come_from_the_jobs_own_rows_only():
    job_id = uuid.uuid4()
    db = FakeDb([FakeResult(scalars=[f"{job_id}_0", f"{job_id}_1"])])
    store, _ = _store(db=db)
    assert await store.job_vector_ids(str(job_id)) == [f"{job_id}_0", f"{job_id}_1"]
    assert "document_chunks.job_id" in _sql(db.statements[0]) and "document_chunks.customer_id" in _sql(db.statements[0])


@pytest.mark.asyncio
async def test_a_job_id_that_is_not_a_uuid_is_refused_before_any_statement():
    db = FakeDb()
    store, _ = _store(db=db)
    for bad in ("not-a-uuid", "", "1; DROP TABLE ingestion_jobs"):
        with pytest.raises(ValueError):
            await store.job_vector_ids(bad)
    assert db.statements == []


# --- writing a page through the EXISTING chunk pipeline ----------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_page_is_written_with_its_deterministic_job_id_url_title_and_chunk_metadata():
    page, embed_log = _page(n=3), []
    log: list = []
    db, vectors = FakeDb([FakeResult(scalar=3)]), FakeVectors(log=log)
    db.log = log
    store, _ = _store(db=db, vectors=vectors, embed_log=embed_log)
    written = await store.write_page(page)
    job = db.added[0]
    assert job.id == page.job_id and job.customer_id == CUSTOMER and job.source_type == "url"
    assert job.source_url == page.canonical_url and job.source_filename == page.title and job.status == "completed" and job.chunks_created == 3
    rows = [o for o in db.added if hasattr(o, "vector_id")]
    assert [(r.vector_id, r.source_url, r.source_title, r.job_id) for r in rows] == [(f"{page.job_id}_{i}", page.canonical_url, page.title, page.job_id) for i in range(3)]
    assert [(v["id"], v["metadata"]["source_url"], v["metadata"]["source_title"], v["metadata"]["site_id"]) for v in vectors.upserted] == \
           [(f"{page.job_id}_{i}", page.canonical_url, page.title, "admizz-test") for i in range(3)]
    assert ("upsert", "admizz-test") in vectors.log                                                         # the namespace is the site id
    assert embed_log == [3] and (written.job_id, written.rows, written.vectors) == (str(page.job_id), 3, 3)


@pytest.mark.asyncio
async def test_postgres_is_committed_before_pinecone_is_written():
    page, log = _page(), []
    db, vectors = FakeDb(), FakeVectors(log=log)
    db.log = log
    await _store(db=db, vectors=vectors)[0].write_page(page)
    assert log.index("commit") < next(i for i, e in enumerate(log) if isinstance(e, tuple) and e[0] == "upsert")


@pytest.mark.asyncio
async def test_a_vector_failure_marks_the_job_failed_and_raises_with_the_job_id():
    page = _page()
    db, vectors = FakeDb(), FakeVectors(fail_upsert=True)
    with pytest.raises(PageWriteError) as caught:
        await _store(db=db, vectors=vectors)[0].write_page(page)
    assert caught.value.job_id == str(page.job_id) and "pinecone down" in str(caught.value)
    job = db.added[0]
    assert job.status == "failed" and "pinecone down" in job.error_message


# --- cleanup and retirement statements are exact ------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cleanup_deletes_the_jobs_vectors_first_then_only_that_job_for_this_customer():
    job_id = uuid.uuid4()
    log: list = []
    db, vectors = FakeDb([FakeResult(scalars=[f"{job_id}_0"]), FakeResult(one=SimpleNamespace(chunks_created=2))]), FakeVectors(log=log)
    db.log = log
    await _store(db=db, vectors=vectors)[0].cleanup_job(str(job_id))
    kinds = [e if isinstance(e, str) else e[0] for e in log]
    assert kinds.index("delete_vectors") < len(kinds) - 1 - kinds[::-1].index("execute")           # the row delete comes after the vector delete
    ids, namespace = vectors.deleted[0]
    assert namespace == "admizz-test" and set(ids) == {f"{job_id}_0", f"{job_id}_1"}
    delete_sql = _sql(db.statements[-1])
    assert delete_sql.startswith("DELETE FROM ingestion_jobs") and "ingestion_jobs.id" in delete_sql and "ingestion_jobs.customer_id" in delete_sql


@pytest.mark.asyncio
async def test_delete_vectors_and_delete_job_touch_exactly_what_they_are_given():
    job_id = uuid.uuid4()
    db, vectors = FakeDb(), FakeVectors()
    store, _ = _store(db=db, vectors=vectors)
    await store.delete_vectors([f"{job_id}_0", f"{job_id}_1"])
    await store.delete_job(str(job_id))
    assert vectors.deleted == [((f"{job_id}_0", f"{job_id}_1"), "admizz-test")]
    sql = _sql(db.statements[0])
    assert sql.startswith("DELETE FROM ingestion_jobs") and "WHERE ingestion_jobs.id =" in sql and "ingestion_jobs.customer_id =" in sql
    assert str(job_id) in {str(v) for v in db.statements[0].compile(dialect=postgresql.dialect()).params.values()}


@pytest.mark.asyncio
async def test_an_empty_vector_list_deletes_nothing():
    vectors = FakeVectors()
    await _store(vectors=vectors)[0].delete_vectors([])
    assert vectors.deleted == [] or vectors.deleted == [((), "admizz-test")]


# --- the read-only vector check added to the vector service --------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_vector_service_reports_which_ids_exist_with_a_read_only_fetch():
    calls = []

    class Index:
        def fetch(self, ids, namespace):
            calls.append((tuple(ids), namespace))
            return SimpleNamespace(vectors={i: object() for i in ids if i.endswith("0")})
    service = VectorStoreService.__new__(VectorStoreService)
    service.index = Index()
    ids = [f"j_{i}" for i in range(250)]
    found = await service.existing_ids(ids, "admizz-test")
    assert found == {i for i in ids if i.endswith("0")} and [len(c[0]) for c in calls] == [100, 100, 50] and {c[1] for c in calls} == {"admizz-test"}
    assert await service.existing_ids([], "admizz-test") == set()


# --- building a prepared page from an extracted page --------------------------------------------------------------------------------------------------

def _entry(**kw):
    return {"id": "uk-visa-fee", "canonical_url": f"{HOST}/answers/uk-student-visa-fee-nepal", "title": "UK Student Visa Fee",
            "category": "visa", "country": "uk", "kind": "answer", **kw}


HTML = ("<html><head><title>UK Student Visa Fee</title></head><body><main><h1>UK Student Visa Fee</h1>"
        "<p>A UK Student visa applied for from outside the UK has a fee that is set by the government and listed on the official page.</p>"
        "<h2>Sources</h2><p>Checked in October 2026. Rules change, so confirm on the official site before you apply.</p></main></body></html>")


def test_prepare_page_sets_url_title_hash_and_chunk_metadata():
    page = prepare_page(_entry(), extract_page(HTML))
    assert page.canonical_url.endswith("fee-nepal") and page.title == "UK Student Visa Fee" and page.site_id == "admizz-test"
    assert page.chunks and all(c["source_url"] == page.canonical_url and c["source_title"] == page.title for c in page.chunks)
    assert page.tokens == sum(c["token_count"] for c in page.chunks) and (page.category, page.country, page.kind) == ("visa", "uk", "answer")
    assert page.content_sha256 == hashlib.sha256(extract_page(HTML).text.encode()).hexdigest()


def test_the_same_extracted_text_gives_the_same_job_id_and_changed_text_a_new_one():
    a, b = prepare_page(_entry(), extract_page(HTML)), prepare_page(_entry(), extract_page(HTML))
    c = prepare_page(_entry(), extract_page(HTML.replace("fee that is set", "fee that was set")))
    assert a.job_id == b.job_id and a.job_id != c.job_id


def test_an_empty_extraction_is_refused():
    with pytest.raises(ValueError):
        prepare_page(_entry(), extract_page("<html><body></body></html>"))
