"""
Vector orphans brief (2026-09-24, session 53), Part B: unit coverage for the
reconciliation script's pure logic. The script itself is a manual/CLI tool
(not exercised end-to-end against a real DB/Pinecone here), but the id
classification and orphan-math it runs on live data is worth locking down.
"""
from scripts.vector_reconciliation import _prefix_bucket


def test_prefix_bucket_classifies_stella_product():
    assert _prefix_bucket("stella_product_ext-123") == "stella_product_"


def test_prefix_bucket_classifies_local_product():
    assert _prefix_bucket("product_5b1e2c3a-...") == "product_"


def test_prefix_bucket_classifies_content_chunk():
    # "<job_id>_<chunk_index>" shape -- doesn't match either product prefix.
    assert _prefix_bucket("98cf5982-d603-493e-b54d-52647090ea8d_0") == "content_chunk"


def test_orphan_math_excludes_stella_ids_and_matches_postgres_rows():
    pinecone_ids = {
        "stella_product_ext-1",       # by-design no local row -- not an orphan
        "product_abc",                 # matches a Postgres Product row
        "product_orphan",              # no matching Postgres row -- orphan
        "job1_0",                      # matches a Postgres DocumentChunk row
        "job1_1",                      # no matching Postgres row -- orphan
    }
    chunk_ids = {"job1_0"}
    product_ids = {"product_abc"}

    local_row_ids = chunk_ids | product_ids
    stella_ids = {vid for vid in pinecone_ids if vid.startswith("stella_product_")}
    reconcilable = pinecone_ids - stella_ids
    orphan_vectors = reconcilable - local_row_ids
    rows_without_vectors = local_row_ids - pinecone_ids

    assert orphan_vectors == {"product_orphan", "job1_1"}
    assert rows_without_vectors == set()
    assert "stella_product_ext-1" not in orphan_vectors
