"""
Agentic Commerce Connector

Syncs product data from Agentic Commerce backend to Zunkiree's vector store.
Each sync is scoped to a specific site_id (tenant), ensuring complete isolation.
"""

import uuid
import json
import hashlib
import logging
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models import Customer, IngestionJob, Product
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service

logger = logging.getLogger("zunkiree.agenticom")
settings = get_settings()


class AgenticomConnector:
    """
    Connector for syncing products from Agentic Commerce.

    Data Flow:
    1. Fetch products from Agentic Commerce API (/api/sync/products)
    2. Transform to Zunkiree's format
    3. Generate embeddings via OpenAI
    4. Upsert to Pinecone (namespace = site_id)
    5. Store in PostgreSQL products table

    Tenant Isolation:
    - Each sync is scoped to a single site_id
    - Pinecone uses namespaces (site_id) for complete vector isolation
    - PostgreSQL rows are filtered by customer_id
    - No cross-tenant data leakage is possible
    """

    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.vector_store = get_vector_store_service()
        self.base_url = settings.agenticom_api_url
        self.sync_secret = settings.agenticom_sync_secret

    async def sync_products(
        self,
        db: AsyncSession,
        site_id: str,
        full_sync: bool = False,
    ) -> IngestionJob:
        """
        Sync products from Agentic Commerce for a specific site.

        Args:
            db: Database session
            site_id: The merchant's site_id (maps to X-Site-ID header)
            full_sync: If True, sync all products. If False, only sync updated ones.

        Returns:
            IngestionJob tracking the sync progress
        """
        # Get customer by site_id
        result = await db.execute(
            select(Customer).where(Customer.site_id == site_id)
        )
        customer = result.scalar_one_or_none()

        if not customer:
            raise ValueError(f"Customer not found for site_id: {site_id}")

        # Create ingestion job
        job = IngestionJob(
            customer_id=customer.id,
            source_type="agenticom_sync",
            source_url=f"{self.base_url}/api/sync/products",
            status="processing",
            started_at=datetime.utcnow(),
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

        try:
            # Determine updated_since for incremental sync
            updated_since: Optional[datetime] = None
            if not full_sync:
                # Get the last successful sync time
                last_job = await db.execute(
                    select(IngestionJob)
                    .where(
                        IngestionJob.customer_id == customer.id,
                        IngestionJob.source_type == "agenticom_sync",
                        IngestionJob.status == "completed",
                    )
                    .order_by(IngestionJob.completed_at.desc())
                    .limit(1)
                )
                last_job_record = last_job.scalar_one_or_none()
                if last_job_record and last_job_record.completed_at:
                    updated_since = last_job_record.completed_at

            # Fetch and process products
            products_synced = await self._fetch_and_store_products(
                db=db,
                customer_id=customer.id,
                site_id=site_id,
                updated_since=updated_since,
            )

            # Update job status
            job.status = "completed"
            job.chunks_created = products_synced
            job.completed_at = datetime.utcnow()
            await db.commit()

            logger.info(
                "[AGENTICOM-SYNC] Completed sync for site_id=%s, products=%d",
                site_id,
                products_synced,
            )

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            await db.commit()
            logger.error("[AGENTICOM-SYNC] Failed for site_id=%s: %s", site_id, e)
            raise

        return job

    async def _fetch_and_store_products(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        site_id: str,
        updated_since: Optional[datetime] = None,
    ) -> int:
        """
        Fetch products from Agentic Commerce API and store them.

        Returns:
            Number of products synced
        """
        products_synced = 0
        page = 1
        limit = 100

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                # Build request URL
                params = {"page": page, "limit": limit}
                if updated_since:
                    params["updated_since"] = updated_since.isoformat()

                # Make request with auth headers
                response = await client.get(
                    f"{self.base_url}/api/sync/products",
                    params=params,
                    headers={
                        "X-Site-ID": site_id,
                        "X-Sync-Secret": self.sync_secret,
                    },
                )

                if response.status_code == 401:
                    raise ValueError("Invalid sync secret - check ZUNKIREE_WEBHOOK_SECRET")
                if response.status_code == 404:
                    raise ValueError(f"Merchant not found for site_id: {site_id}")
                response.raise_for_status()

                data = response.json()
                products = data.get("products", [])

                if not products:
                    break

                # Process each product
                for product_data in products:
                    await self._store_product(
                        db=db,
                        customer_id=customer_id,
                        site_id=site_id,
                        product_data=product_data,
                    )
                    products_synced += 1

                # Check if more pages
                if not data.get("has_more", False):
                    break

                page += 1

        await db.commit()
        return products_synced

    async def _store_product(
        self,
        db: AsyncSession,
        customer_id: uuid.UUID,
        site_id: str,
        product_data: dict,
    ) -> None:
        """
        Store a single product in the database and vector store.
        """
        product_id = product_data["id"]
        source_hash = hashlib.sha256(f"agenticom:{product_id}".encode()).hexdigest()

        # Check for existing product
        existing = await db.execute(
            select(Product).where(
                Product.customer_id == customer_id,
                Product.source_hash == source_hash,
            )
        )
        existing_product = existing.scalar_one_or_none()

        # Extract variant info for sizes/colors
        variants = product_data.get("variants", [])
        sizes = set()
        colors = set()
        skus = []

        for variant in variants:
            if variant.get("option1"):
                # Check if it looks like a size
                opt1 = variant["option1"]
                if opt1.upper() in ["XS", "S", "M", "L", "XL", "XXL", "XXXL"] or opt1.isdigit():
                    sizes.add(opt1)
                else:
                    colors.add(opt1)
            if variant.get("option2"):
                opt2 = variant["option2"]
                if opt2.upper() in ["XS", "S", "M", "L", "XL", "XXL", "XXXL"] or opt2.isdigit():
                    sizes.add(opt2)
                else:
                    colors.add(opt2)
            if variant.get("sku"):
                skus.append(variant["sku"])

        # Determine in_stock from variants
        in_stock = any(v.get("available", True) for v in variants) if variants else True

        # Get first SKU
        first_sku = skus[0] if skus else None

        # Extract images
        images = [img.get("url") for img in product_data.get("images", []) if img.get("url")]

        # Build product URL (from agentic-commerce's storefront)
        product_url = f"{self.base_url}/products/{product_data.get('slug', product_id)}"

        if existing_product:
            # Update existing product
            existing_product.name = product_data["name"]
            existing_product.description = product_data.get("description")
            existing_product.price = float(product_data["price"]) if product_data.get("price") else None
            existing_product.currency = product_data.get("currency", "USD")
            existing_product.original_price = float(product_data["compare_at_price"]) if product_data.get("compare_at_price") else None
            existing_product.images = json.dumps(images)
            existing_product.url = product_url
            existing_product.sku = first_sku
            existing_product.brand = product_data.get("vendor")
            existing_product.category = product_data.get("product_type")
            existing_product.sizes = json.dumps(list(sizes))
            existing_product.colors = json.dumps(list(colors))
            existing_product.in_stock = in_stock
            existing_product.tags = json.dumps(product_data.get("tags", []))
            existing_product.scraped_at = datetime.utcnow()
            product_db_id = existing_product.id
        else:
            # Create new product
            product = Product(
                customer_id=customer_id,
                name=product_data["name"],
                description=product_data.get("description"),
                price=float(product_data["price"]) if product_data.get("price") else None,
                currency=product_data.get("currency", "USD"),
                original_price=float(product_data["compare_at_price"]) if product_data.get("compare_at_price") else None,
                images=json.dumps(images),
                url=product_url,
                sku=first_sku,
                brand=product_data.get("vendor"),
                category=product_data.get("product_type"),
                sizes=json.dumps(list(sizes)),
                colors=json.dumps(list(colors)),
                in_stock=in_stock,
                tags=json.dumps(product_data.get("tags", [])),
                source_hash=source_hash,
                scraped_at=datetime.utcnow(),
            )
            db.add(product)
            await db.flush()
            product_db_id = product.id

        # Generate embedding text
        embedding_text = self._build_embedding_text(product_data)

        # Create embedding
        embeddings = await self.embedding_service.create_embeddings([embedding_text])

        if embeddings:
            vector_id = f"product_{product_db_id}"

            # Upsert to Pinecone (isolated by namespace)
            await self.vector_store.upsert_vectors(
                [{
                    "id": vector_id,
                    "values": embeddings[0],
                    "metadata": {
                        "type": "product",
                        "product_id": str(product_db_id),
                        "site_id": site_id,
                        "source": "agenticom",
                        "agenticom_id": str(product_id),
                    },
                }],
                namespace=site_id,
            )

            # Update vector_id on product
            if existing_product:
                existing_product.vector_id = vector_id
            else:
                product.vector_id = vector_id

    def _build_embedding_text(self, product_data: dict) -> str:
        """
        Build text for embedding generation.
        Includes name, description, tags, and variant options for semantic search.
        """
        parts = [product_data["name"]]

        if product_data.get("description"):
            parts.append(product_data["description"])

        if product_data.get("vendor"):
            parts.append(f"Brand: {product_data['vendor']}")

        if product_data.get("product_type"):
            parts.append(f"Category: {product_data['product_type']}")

        if product_data.get("tags"):
            parts.append(f"Tags: {', '.join(product_data['tags'])}")

        # Add variant options for searchability
        options = product_data.get("options", [])
        for option in options:
            if option.get("values"):
                parts.append(f"{option['name']}: {', '.join(option['values'])}")

        return "\n".join(parts)


# Singleton instance
_agenticom_connector: AgenticomConnector | None = None


def get_agenticom_connector() -> AgenticomConnector:
    """Get singleton AgenticomConnector instance."""
    global _agenticom_connector
    if _agenticom_connector is None:
        _agenticom_connector = AgenticomConnector()
    return _agenticom_connector
