"""
Direct product search endpoint — vector search + SQL without LLM.
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Customer
from app.models.product import Product
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service

logger = logging.getLogger("zunkiree.products")

router = APIRouter(prefix="/products", tags=["products"])


def _product_to_dict(p: Product) -> dict:
    """Serialize a Product model to API response dict."""
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description or "",
        "price": p.price,
        "currency": p.currency or "",
        "original_price": p.original_price,
        "images": json.loads(p.images) if p.images else [],
        "url": p.url or "",
        "brand": p.brand or "",
        "category": p.category or "",
        "sizes": json.loads(p.sizes) if p.sizes else [],
        "colors": json.loads(p.colors) if p.colors else [],
        "in_stock": p.in_stock if p.in_stock is not None else True,
    }


@router.get("/search")
async def search_products(
    site_id: str,
    q: str = "",
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    in_stock: bool | None = None,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Direct product search — vector similarity + SQL filters.
    No LLM involvement; returns products instantly.
    """
    # Resolve customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == site_id, Customer.is_active == True)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    products: list[Product] = []

    if q.strip():
        # Vector search path: embed query → Pinecone → PostgreSQL join
        embedding_service = get_embedding_service()
        vector_store = get_vector_store_service()

        query_embedding = await embedding_service.create_embedding(q)
        matches = await vector_store.query_vectors(
            query_vector=query_embedding,
            namespace=site_id,
            top_k=limit * 2,  # fetch more to allow for filtering
            site_id=site_id,
            filter_metadata={"type": "product"},
        )

        product_ids = []
        for match in matches:
            pid = match.get("metadata", {}).get("product_id")
            if pid:
                product_ids.append(pid)

        if product_ids:
            import uuid
            result = await db.execute(
                select(Product).where(
                    Product.customer_id == customer.id,
                    Product.id.in_([uuid.UUID(pid) for pid in product_ids if pid]),
                )
            )
            products = list(result.scalars().all())
    else:
        # No query — return all products with filters
        stmt = select(Product).where(Product.customer_id == customer.id)
        if category:
            stmt = stmt.where(Product.category.ilike(f"%{category}%"))
        stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        products = list(result.scalars().all())

    # Apply filters
    filtered = []
    for p in products:
        if in_stock is not None and p.in_stock != in_stock:
            continue
        if min_price is not None and (p.price is None or p.price < min_price):
            continue
        if max_price is not None and (p.price is None or p.price > max_price):
            continue
        if category and q.strip():
            # Category filter for vector search results
            p_category = p.category or ""
            if category.lower() not in p_category.lower():
                continue
        filtered.append(p)

    return {
        "products": [_product_to_dict(p) for p in filtered[:limit]],
        "total": len(filtered),
    }
