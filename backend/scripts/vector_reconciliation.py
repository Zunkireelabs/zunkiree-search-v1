"""
Vector orphans brief (2026-09-24, session 53), Part B: READ-ONLY reconciliation
between a tenant's Pinecone namespace and its Postgres rows.

For one site_id, lists every vector id in its Pinecone namespace and compares
it against Postgres (`document_chunks.vector_id` + `products.vector_id` for
live products). Reports:

- orphan vectors: in Pinecone, no matching Postgres row. The bug Part A
  (PR #90) fixes going forward -- these are pre-existing, from before that
  fix landed.
- rows without vectors: in Postgres, no matching Pinecone vector. The safe
  direction (keyword search still finds the content) -- reported for
  completeness, not treated as a problem.
- Stella-sourced product vectors (`stella_product_...` prefix) are reported
  separately and never counted as orphans: `handle_product_deleted`
  explicitly does not mirror them into the local `products` table (different
  id space -- see inbound_event_dispatcher.py's own docstring), so they will
  never have a matching Postgres row by design.

NO delete code path exists in this script, on purpose -- cleanup needs
Sadin's separate go per the brief (Part C), after Part A is on `main`.

Usage (from backend/):
    .venv311/bin/python -m scripts.vector_reconciliation <site_id> [<site_id> ...]

Example:
    .venv311/bin/python -m scripts.vector_reconciliation kasa-clothing dental-city healthy-smile
"""
import argparse
import asyncio
from collections import defaultdict

from sqlalchemy import select

from app.database import async_session_maker
from app.models.customer import Customer
from app.models.ingestion import DocumentChunk
from app.models.product import Product
from app.services.vector_store import get_vector_store_service


def _prefix_bucket(vector_id: str) -> str:
    if vector_id.startswith("stella_product_"):
        return "stella_product_"
    if vector_id.startswith("product_"):
        return "product_"
    return "content_chunk"  # "<job_id>_<i>" shaped


async def _list_pinecone_ids(namespace: str) -> set[str]:
    vector_store = get_vector_store_service()
    ids: set[str] = set()

    def _list_sync():
        collected = set()
        for page in vector_store.index.list(namespace=namespace):
            for item in page.vectors:
                collected.add(item.id)
        return collected

    ids = await asyncio.to_thread(_list_sync)
    return ids


async def _postgres_ids(db, customer_id) -> tuple[set[str], set[str]]:
    """Returns (document_chunk vector_ids, product vector_ids) for one customer."""
    chunk_result = await db.execute(
        select(DocumentChunk.vector_id).where(DocumentChunk.customer_id == customer_id)
    )
    chunk_ids = {row[0] for row in chunk_result.all() if row[0]}

    product_result = await db.execute(
        select(Product.vector_id).where(
            Product.customer_id == customer_id,
            Product.vector_id.isnot(None),
        )
    )
    product_ids = {row[0] for row in product_result.all() if row[0]}

    return chunk_ids, product_ids


async def reconcile(site_id: str) -> dict:
    async with async_session_maker() as db:
        result = await db.execute(select(Customer).where(Customer.site_id == site_id))
        customer = result.scalar_one_or_none()
        if not customer:
            return {"site_id": site_id, "error": "CUSTOMER_NOT_FOUND"}

        chunk_ids, product_ids = await _postgres_ids(db, customer.id)

    pinecone_ids = await _list_pinecone_ids(namespace=site_id)

    local_row_ids = chunk_ids | product_ids  # what Postgres actually knows about
    stella_ids = {vid for vid in pinecone_ids if vid.startswith("stella_product_")}
    reconcilable_pinecone_ids = pinecone_ids - stella_ids  # exclude by-design no-row ids

    orphan_vectors = reconcilable_pinecone_ids - local_row_ids
    rows_without_vectors = local_row_ids - pinecone_ids

    orphans_by_prefix: dict[str, list[str]] = defaultdict(list)
    for vid in sorted(orphan_vectors):
        orphans_by_prefix[_prefix_bucket(vid)].append(vid)

    return {
        "site_id": site_id,
        "customer_id": str(customer.id),
        "pinecone_vector_count": len(pinecone_ids),
        "stella_vector_count": len(stella_ids),
        "postgres_document_chunk_count": len(chunk_ids),
        "postgres_product_vector_count": len(product_ids),
        "orphan_vector_count": len(orphan_vectors),
        "rows_without_vector_count": len(rows_without_vectors),
        "orphans_by_prefix": {k: v for k, v in orphans_by_prefix.items()},
    }


def _print_report(report: dict) -> None:
    if "error" in report:
        print(f"\n=== {report['site_id']} ===")
        print(f"  ERROR: {report['error']}")
        return

    print(f"\n=== {report['site_id']} (customer_id={report['customer_id']}) ===")
    print(f"  Pinecone vectors (namespace total):     {report['pinecone_vector_count']}")
    print(f"    of which stella_product_* (excluded):  {report['stella_vector_count']}")
    print(f"  Postgres document_chunks.vector_id:     {report['postgres_document_chunk_count']}")
    print(f"  Postgres products.vector_id:            {report['postgres_product_vector_count']}")
    print(f"  Orphan vectors (Pinecone, no PG row):    {report['orphan_vector_count']}")
    print(f"  Rows without a vector (safe direction):  {report['rows_without_vector_count']}")
    if report["orphans_by_prefix"]:
        print("  Orphan ids by prefix:")
        for prefix, ids in report["orphans_by_prefix"].items():
            print(f"    {prefix}: {len(ids)}")
            for vid in ids:
                print(f"      - {vid}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("site_ids", nargs="+", help="One or more tenant site_ids to reconcile")
    args = parser.parse_args()

    print("READ-ONLY reconciliation -- no writes, no deletes.")
    reports = []
    for site_id in args.site_ids:
        report = await reconcile(site_id)
        reports.append(report)
        _print_report(report)

    print("\nNothing was written or deleted.")


if __name__ == "__main__":
    asyncio.run(main())
