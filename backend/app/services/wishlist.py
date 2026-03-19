"""
Wishlist service — DB-first, no in-memory cache.
"""
import json
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.wishlist import Wishlist
from app.models.product import Product

logger = logging.getLogger("zunkiree.wishlist")


class WishlistService:
    async def add_to_wishlist(
        self,
        db: AsyncSession,
        session_id: str,
        customer_id: uuid.UUID,
        product_id: str,
    ) -> dict:
        """Add a product to the wishlist. Returns the updated wishlist."""
        pid = uuid.UUID(product_id)

        # Check product exists
        result = await db.execute(
            select(Product).where(Product.id == pid, Product.customer_id == customer_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            return {"error": "Product not found"}

        # Check if already in wishlist
        result = await db.execute(
            select(Wishlist).where(
                Wishlist.session_id == session_id,
                Wishlist.product_id == pid,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return {"message": f"{product.name} is already in your wishlist", "wishlist": await self._get_wishlist_data(db, session_id)}

        # Add to wishlist
        entry = Wishlist(
            session_id=session_id,
            customer_id=customer_id,
            product_id=pid,
        )
        db.add(entry)
        await db.commit()

        wishlist = await self._get_wishlist_data(db, session_id)
        return {"message": f"Added {product.name} to your wishlist!", "wishlist": wishlist}

    async def remove_from_wishlist(
        self,
        db: AsyncSession,
        session_id: str,
        product_id: str,
    ) -> dict:
        """Remove a product from the wishlist."""
        pid = uuid.UUID(product_id)
        await db.execute(
            delete(Wishlist).where(
                Wishlist.session_id == session_id,
                Wishlist.product_id == pid,
            )
        )
        await db.commit()

        wishlist = await self._get_wishlist_data(db, session_id)
        return {"message": "Removed from wishlist.", "wishlist": wishlist}

    async def get_wishlist(
        self,
        db: AsyncSession,
        session_id: str,
    ) -> dict:
        """Get all wishlist items with product details."""
        wishlist = await self._get_wishlist_data(db, session_id)
        return {"wishlist": wishlist}

    async def _get_wishlist_data(self, db: AsyncSession, session_id: str) -> list[dict]:
        """Fetch wishlist items joined with product data."""
        result = await db.execute(
            select(Wishlist).where(Wishlist.session_id == session_id).order_by(Wishlist.created_at.desc())
        )
        entries = result.scalars().all()

        items = []
        for entry in entries:
            p = entry.product
            if p is None:
                continue
            images = json.loads(p.images) if p.images else []
            items.append({
                "product_id": str(p.id),
                "name": p.name,
                "price": p.price,
                "currency": p.currency or "",
                "original_price": p.original_price,
                "image": images[0] if images else "",
                "url": p.url or "",
                "in_stock": p.in_stock,
                "sizes": json.loads(p.sizes) if p.sizes else [],
                "colors": json.loads(p.colors) if p.colors else [],
            })

        return items


# Singleton
_wishlist_service: WishlistService | None = None


def get_wishlist_service() -> WishlistService:
    global _wishlist_service
    if _wishlist_service is None:
        _wishlist_service = WishlistService()
    return _wishlist_service
