import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Customer
from app.services.cart import get_cart_service

router = APIRouter(prefix="/cart", tags=["cart"])


class AddToCartRequest(BaseModel):
    site_id: str = Field(..., description="Customer site identifier")
    product_id: str = Field(..., description="Product ID to add")
    quantity: int = Field(1, ge=1, le=10)
    size: str = ""
    color: str = ""


@router.get("/{session_id}")
async def get_cart(session_id: str):
    """Get cart contents for a session."""
    cart_service = get_cart_service()
    cart = cart_service.get_cart(session_id)
    return cart.to_dict()


@router.get("/{session_id}/count")
async def get_cart_count(session_id: str):
    """Lightweight endpoint for cart badge."""
    cart_service = get_cart_service()
    cart = cart_service.get_cart(session_id)
    return {
        "item_count": cart.item_count,
        "subtotal": round(cart.subtotal, 2),
        "currency": cart.currency,
    }


@router.post("/{session_id}/add")
async def add_to_cart(
    session_id: str,
    request: AddToCartRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add an item to the cart."""
    from app.models.product import Product
    import uuid

    # Resolve customer
    result = await db.execute(
        select(Customer).where(Customer.site_id == request.site_id, Customer.is_active == True)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Get product
    result = await db.execute(
        select(Product).where(
            Product.id == uuid.UUID(request.product_id),
            Product.customer_id == customer.id,
        )
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    images = json.loads(product.images) if product.images else []
    cart_service = get_cart_service()
    cart = cart_service.add_item(
        session_id=session_id,
        product_id=request.product_id,
        name=product.name,
        price=product.price or 0,
        currency=product.currency or "",
        quantity=request.quantity,
        size=request.size,
        color=request.color,
        image=images[0] if images else "",
        url=product.url or "",
    )

    return cart.to_dict()


@router.delete("/{session_id}/{item_index}")
async def remove_from_cart(session_id: str, item_index: int):
    """Remove an item from the cart by index."""
    cart_service = get_cart_service()
    cart = cart_service.remove_item(session_id, item_index)
    return cart.to_dict()


@router.post("/{session_id}/checkout")
async def checkout(session_id: str):
    """Return cart summary for checkout redirect."""
    cart_service = get_cart_service()
    cart = cart_service.get_cart(session_id)

    if not cart.items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    return {
        "items": [item.to_dict() for item in cart.items],
        "subtotal": round(cart.subtotal, 2),
        "currency": cart.currency,
        "item_count": cart.item_count,
    }
