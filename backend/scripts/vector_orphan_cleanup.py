"""
Vector orphans brief (2026-09-24, session 53), Part C: orphan vector cleanup.

Deletes orphan vectors from ONE tenant's Pinecone namespace, identified by
`scripts.vector_reconciliation.reconcile()` (which already excludes
`stella_product_*` ids by design -- see that module's docstring). Deletion
is always by EXACT vector id, never `delete_namespace` / a re-ingest -- a
namespace delete would also wipe the tenant's live `stella_product_*`
vectors, e.g. kasa-clothing's only real Stella-sourced content.

Safety model:
- Default mode is DRY RUN: computes the orphan list, prints counts by
  prefix, asserts none of them start with "stella_product_", writes a JSONL
  export (id + Pinecone metadata) OUTSIDE the repo, and deletes nothing.
- --execute requires --expect-count N. The orphan list is recomputed fresh
  in this same run; if the fresh count doesn't match N, the run refuses and
  deletes/exports nothing (guards against the namespace having changed
  between an earlier dry run and this call). On a match, this run's own
  export is written first (so a pre-delete backup always exists for *this*
  run), then vectors are deleted in batches of 100 via
  vector_store.delete_vectors, logging each batch, and stopping at the
  first error.

Usage (from backend/):
    .venv311/bin/python -m scripts.vector_orphan_cleanup <site_id>
    .venv311/bin/python -m scripts.vector_orphan_cleanup <site_id> --execute --expect-count 660

Export files land in ~/backups/vector-orphans/<site_id>-<UTC timestamp>.jsonl
(override with --export-dir). Never commit these; never copy them to a
laptop.
"""
import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from scripts.vector_reconciliation import reconcile
from app.services.vector_store import get_vector_store_service

logger = logging.getLogger("zunkiree.vector_orphan_cleanup")

DEFAULT_EXPORT_DIR = Path("~/backups/vector-orphans").expanduser()
DELETE_BATCH_SIZE = 100
FETCH_BATCH_SIZE = 100


def _flatten_orphan_ids(report: dict) -> list[str]:
    """Flattens reconcile()'s orphans_by_prefix into a sorted id list.

    Defensive re-assertion (reconcile() already excludes them by
    construction): refuses to proceed if any id starts with
    "stella_product_" -- that prefix must never be deleted.
    """
    ids = sorted(
        vid
        for prefix_ids in report.get("orphans_by_prefix", {}).values()
        for vid in prefix_ids
    )
    for vid in ids:
        assert not vid.startswith("stella_product_"), (
            f"refusing: stella_product_ id in orphan list: {vid}"
        )
    return ids


def _batched(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _export_path(site_id: str, export_dir: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return export_dir / f"{site_id}-{ts}.jsonl"


async def _fetch_metadata(vector_store, ids: list[str], namespace: str) -> dict[str, dict]:
    """Fetches Pinecone metadata for `ids`, batched. Read-only."""
    metadata_by_id: dict[str, dict] = {}
    for batch in _batched(ids, FETCH_BATCH_SIZE):
        result = await asyncio.to_thread(vector_store.index.fetch, ids=batch, namespace=namespace)
        vectors = getattr(result, "vectors", {}) or {}
        for vid, vec in vectors.items():
            meta = getattr(vec, "metadata", None) or {}
            metadata_by_id[vid] = dict(meta)
    return metadata_by_id


def _write_export(path: Path, ids: list[str], metadata_by_id: dict[str, dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    line_count = 0
    with path.open("w") as f:
        for vid in ids:
            f.write(json.dumps({"id": vid, "metadata": metadata_by_id.get(vid, {})}) + "\n")
            line_count += 1
    return line_count


async def _export(site_id: str, ids: list[str], export_dir: Path) -> tuple[Path, int]:
    vector_store = get_vector_store_service()
    metadata_by_id = await _fetch_metadata(vector_store, ids, namespace=site_id)
    path = _export_path(site_id, export_dir)
    line_count = _write_export(path, ids, metadata_by_id)
    return path, line_count


async def _delete(site_id: str, ids: list[str]) -> None:
    vector_store = get_vector_store_service()
    for i, batch in enumerate(_batched(ids, DELETE_BATCH_SIZE)):
        logger.info(
            "[ORPHAN-CLEANUP] site_id=%s batch=%d size=%d sample=%s",
            site_id, i, len(batch), batch[:3],
        )
        try:
            await vector_store.delete_vectors(batch, namespace=site_id)
        except Exception:
            logger.exception("[ORPHAN-CLEANUP] site_id=%s batch=%d FAILED -- stopping", site_id, i)
            raise
        print(f"  deleted batch {i}: {len(batch)} ids")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("site_id", help="One tenant site_id")
    parser.add_argument("--execute", action="store_true", help="Actually delete. Default is dry run.")
    parser.add_argument(
        "--expect-count", type=int, default=None,
        help="Required with --execute: refuses unless the freshly computed orphan count matches.",
    )
    parser.add_argument(
        "--export-dir", type=Path, default=DEFAULT_EXPORT_DIR,
        help="Where to write the JSONL export (default ~/backups/vector-orphans, outside the repo).",
    )
    args = parser.parse_args()

    if args.execute and args.expect_count is None:
        parser.error("--execute requires --expect-count N")

    print(f"Reconciling {args.site_id} ...")
    report = await reconcile(args.site_id)
    if "error" in report:
        print(f"  ERROR: {report['error']}")
        return

    ids = _flatten_orphan_ids(report)
    print(f"Orphan vectors: {len(ids)}")
    for prefix, prefix_ids in report["orphans_by_prefix"].items():
        print(f"  {prefix}: {len(prefix_ids)}")
    print(f"  (stella_product_ in namespace, excluded by design: {report['stella_vector_count']})")

    if not args.execute:
        path, line_count = await _export(args.site_id, ids, args.export_dir)
        print("DRY RUN -- nothing deleted.")
        print(f"Export written: {path} ({line_count} lines)")
        return

    if len(ids) != args.expect_count:
        print(
            f"REFUSING: freshly computed orphan count ({len(ids)}) != "
            f"--expect-count ({args.expect_count}). Nothing deleted, nothing exported."
        )
        return

    path, line_count = await _export(args.site_id, ids, args.export_dir)
    print(f"Export written: {path} ({line_count} lines)")

    print(f"EXECUTING delete of {len(ids)} vectors in batches of {DELETE_BATCH_SIZE} ...")
    await _delete(args.site_id, ids)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
