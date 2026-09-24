"""
Vector orphans brief (2026-09-24, session 53), Part C: unit coverage for the
cleanup script's safety logic -- the stella_ exclusion, the expect-count
refusal, and that dry run never deletes. Not exercised end-to-end against a
real DB/Pinecone here (matches the reconciliation script's test approach).
"""
import pytest

import scripts.vector_orphan_cleanup as cleanup


def _report(orphans_by_prefix, stella_count=0):
    return {
        "site_id": "kasa-clothing",
        "customer_id": "cust-1",
        "orphans_by_prefix": orphans_by_prefix,
        "stella_vector_count": stella_count,
    }


def test_flatten_orphan_ids_sorts_and_flattens():
    report = _report({"product_": ["product_b", "product_a"], "content_chunk": ["job1_1"]})
    assert cleanup._flatten_orphan_ids(report) == ["job1_1", "product_a", "product_b"]


def test_flatten_orphan_ids_refuses_stella_product_ids():
    # Defensive re-check: reconcile() should never produce these, but the
    # cleanup script must refuse rather than delete them if it somehow did.
    # An explicit raise, not assert -- assert is stripped under `python -O`.
    report = _report({"stella_product_": ["stella_product_ext-1"]})
    with pytest.raises(ValueError, match="stella_product_"):
        cleanup._flatten_orphan_ids(report)


def test_batched_chunks_at_given_size():
    ids = [f"id{i}" for i in range(250)]
    batches = list(cleanup._batched(ids, 100))
    assert [len(b) for b in batches] == [100, 100, 50]
    assert batches[0][0] == "id0"
    assert batches[-1][-1] == "id249"


@pytest.mark.asyncio
async def test_execute_refuses_on_expect_count_mismatch(monkeypatch, capsys):
    report = _report({"product_": ["product_a", "product_b"]})

    async def fake_reconcile(site_id):
        return report

    async def fail_export(*args, **kwargs):
        raise AssertionError("export must not run when the count refuses")

    async def fail_delete(*args, **kwargs):
        raise AssertionError("delete must not run when the count refuses")

    monkeypatch.setattr(cleanup, "reconcile", fake_reconcile)
    monkeypatch.setattr(cleanup, "_export", fail_export)
    monkeypatch.setattr(cleanup, "_delete", fail_delete)

    argv = ["vector_orphan_cleanup.py", "kasa-clothing", "--execute", "--expect-count", "999"]
    monkeypatch.setattr("sys.argv", argv)

    await cleanup.main()

    out = capsys.readouterr().out
    assert "REFUSING" in out
    assert "999" in out


@pytest.mark.asyncio
async def test_dry_run_never_calls_delete(monkeypatch, capsys):
    report = _report({"product_": ["product_a"]})

    async def fake_reconcile(site_id):
        return report

    async def fake_export(site_id, ids, export_dir):
        return export_dir / "fake-export.jsonl", len(ids)

    async def fail_delete(*args, **kwargs):
        raise AssertionError("dry run must never call _delete")

    monkeypatch.setattr(cleanup, "reconcile", fake_reconcile)
    monkeypatch.setattr(cleanup, "_export", fake_export)
    monkeypatch.setattr(cleanup, "_delete", fail_delete)

    argv = ["vector_orphan_cleanup.py", "kasa-clothing"]
    monkeypatch.setattr("sys.argv", argv)

    await cleanup.main()

    out = capsys.readouterr().out
    assert "DRY RUN" in out


@pytest.mark.asyncio
async def test_execute_requires_expect_count_flag(monkeypatch):
    argv = ["vector_orphan_cleanup.py", "kasa-clothing", "--execute"]
    monkeypatch.setattr("sys.argv", argv)

    with pytest.raises(SystemExit):
        await cleanup.main()
