"""
Vector orphans brief (2026-09-24, session 53), A2: deleting a Product row
without also deleting its Pinecone vector leaves an orphan the default-RAG
path can never resolve to content -- this was the `product_...`-prefixed
half of kasa-clothing's CHUNK_MISMATCH. Both product-delete endpoints
(admin.py's tenant-admin route and ecommerce_dashboard.py's tenant-facing
route) now clean up the vector, and a Pinecone failure there must not fail
the request -- the Postgres delete already stands.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.api.admin as admin
import app.api.ecommerce_dashboard as ecommerce_dashboard


def _make_product(vector_id="product_abc123"):
    product = MagicMock()
    product.id = uuid.uuid4()
    product.vector_id = vector_id
    return product


def _make_customer(site_id="kasa-clothing"):
    customer = MagicMock()
    customer.id = uuid.uuid4()
    customer.site_id = site_id
    return customer


# --- admin.py: DELETE /admin/products/{site_id}/{product_id} ---


@pytest.mark.asyncio
async def test_admin_delete_product_deletes_matching_vector():
    customer = _make_customer()
    product = _make_product()

    db = AsyncMock()
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    product_result = MagicMock()
    product_result.scalar_one_or_none.return_value = product
    db.execute.side_effect = [customer_result, product_result, MagicMock()]

    fake_vector_store = MagicMock()
    fake_vector_store.delete_vectors = AsyncMock()

    with patch.object(admin, "get_vector_store_service", return_value=fake_vector_store):
        result = await admin.delete_product(
            site_id=customer.site_id,
            product_id=str(product.id),
            db=db,
            _="admin-key",
        )

    assert result == {"message": "Product deleted successfully"}
    fake_vector_store.delete_vectors.assert_awaited_once_with(
        [product.vector_id], namespace=customer.site_id
    )


@pytest.mark.asyncio
async def test_admin_delete_product_skips_vector_delete_when_none():
    # A product created without an embedding (e.g. embedding call failed at
    # ingest time) has no vector_id -- nothing to clean up, and calling
    # delete_vectors with an empty/None id would be a no-op at best.
    customer = _make_customer()
    product = _make_product(vector_id=None)

    db = AsyncMock()
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    product_result = MagicMock()
    product_result.scalar_one_or_none.return_value = product
    db.execute.side_effect = [customer_result, product_result, MagicMock()]

    fake_vector_store = MagicMock()
    fake_vector_store.delete_vectors = AsyncMock()

    with patch.object(admin, "get_vector_store_service", return_value=fake_vector_store):
        await admin.delete_product(
            site_id=customer.site_id,
            product_id=str(product.id),
            db=db,
            _="admin-key",
        )

    fake_vector_store.delete_vectors.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_delete_product_pinecone_failure_does_not_fail_request():
    # The Postgres delete already committed -- a Pinecone failure here is
    # logged and swallowed, matching the dispatcher's per-handler isolation,
    # not surfaced as a 500 to the admin caller.
    customer = _make_customer()
    product = _make_product()

    db = AsyncMock()
    customer_result = MagicMock()
    customer_result.scalar_one_or_none.return_value = customer
    product_result = MagicMock()
    product_result.scalar_one_or_none.return_value = product
    db.execute.side_effect = [customer_result, product_result, MagicMock()]

    fake_vector_store = MagicMock()
    fake_vector_store.delete_vectors = AsyncMock(side_effect=RuntimeError("pinecone down"))

    with patch.object(admin, "get_vector_store_service", return_value=fake_vector_store):
        result = await admin.delete_product(
            site_id=customer.site_id,
            product_id=str(product.id),
            db=db,
            _="admin-key",
        )

    assert result == {"message": "Product deleted successfully"}
    fake_vector_store.delete_vectors.assert_awaited_once()


# --- ecommerce_dashboard.py: DELETE /products/{product_id} ---


@pytest.mark.asyncio
async def test_dashboard_delete_product_deletes_matching_vector():
    customer = _make_customer()
    product = _make_product()

    db = AsyncMock()
    product_result = MagicMock()
    product_result.scalar_one_or_none.return_value = product
    db.execute.return_value = product_result

    fake_vector_store = MagicMock()
    fake_vector_store.delete_vectors = AsyncMock()

    with patch.object(ecommerce_dashboard, "_authenticate", AsyncMock(return_value=customer)), \
         patch.object(ecommerce_dashboard, "get_vector_store_service", return_value=fake_vector_store):
        result = await ecommerce_dashboard.delete_product(
            product_id=product.id,
            x_api_key="tenant-key",
            db=db,
        )

    assert result == {"detail": "Product deleted"}
    fake_vector_store.delete_vectors.assert_awaited_once_with(
        [product.vector_id], namespace=customer.site_id
    )


@pytest.mark.asyncio
async def test_dashboard_delete_product_pinecone_failure_does_not_fail_request():
    customer = _make_customer()
    product = _make_product()

    db = AsyncMock()
    product_result = MagicMock()
    product_result.scalar_one_or_none.return_value = product
    db.execute.return_value = product_result

    fake_vector_store = MagicMock()
    fake_vector_store.delete_vectors = AsyncMock(side_effect=RuntimeError("pinecone down"))

    with patch.object(ecommerce_dashboard, "_authenticate", AsyncMock(return_value=customer)), \
         patch.object(ecommerce_dashboard, "get_vector_store_service", return_value=fake_vector_store):
        result = await ecommerce_dashboard.delete_product(
            product_id=product.id,
            x_api_key="tenant-key",
            db=db,
        )

    assert result == {"detail": "Product deleted"}
    fake_vector_store.delete_vectors.assert_awaited_once()
