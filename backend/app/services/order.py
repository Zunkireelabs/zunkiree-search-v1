"""
Order service — creates and manages orders from cart data.
"""
import json
import uuid
import secrets
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.order import Order
from app.services.cart import get_cart_service

logger = logging.getLogger("zunkiree.order")


def generate_order_number() -> str:
    """Generate a unique order number: ZK-{hex}-{rand}."""
    hex_part = secrets.token_hex(3).upper()
    rand_part = secrets.randbelow(10000)
    return f"ZK-{hex_part}-{rand_part:04d}"


class OrderService:
    async def create_order_from_cart(
        self,
        db: AsyncSession,
        session_id: str,
        customer_id: uuid.UUID,
        billing_address: dict | None = None,
        shipping_address: dict | None = None,
        shopper_email: str | None = None,
        notes: str | None = None,
        payment_method: str | None = None,
    ) -> dict:
        """Snapshot cart into an order."""
        cart_service = get_cart_service()
        cart = cart_service.get_cart(session_id)

        if not cart.items:
            return {"error": "Cart is empty"}

        # Snapshot cart items
        items_snapshot = [item.to_dict() for item in cart.items]

        is_cod = payment_method == "cod"
        order = Order(
            order_number=generate_order_number(),
            customer_id=customer_id,
            session_id=session_id,
            shopper_email=shopper_email,
            items=json.dumps(items_snapshot),
            subtotal=round(cart.subtotal, 2),
            total=round(cart.subtotal, 2),  # Tax/shipping added later
            currency=cart.currency,
            status="processing" if is_cod else "pending",
            payment_status="cod" if is_cod else "unpaid",
            payment_method=payment_method or "online",
            billing_address=json.dumps(billing_address) if billing_address else None,
            shipping_address=json.dumps(shipping_address) if shipping_address else None,
            notes=notes,
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)

        # Clear cart after order creation
        cart_service.clear_cart(session_id)
        await cart_service.save_to_db(db, session_id, customer_id)

        return {"order": self._order_to_dict(order)}

    async def get_order(self, db: AsyncSession, order_id: uuid.UUID) -> dict:
        """Get order by ID."""
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            return {"error": "Order not found"}
        return {"order": self._order_to_dict(order)}

    async def get_order_by_number(self, db: AsyncSession, order_number: str) -> dict:
        """Get order by order number."""
        result = await db.execute(select(Order).where(Order.order_number == order_number))
        order = result.scalar_one_or_none()
        if not order:
            return {"error": "Order not found"}
        return {"order": self._order_to_dict(order)}

    async def get_session_orders(self, db: AsyncSession, session_id: str) -> dict:
        """Get all orders for a session."""
        result = await db.execute(
            select(Order).where(Order.session_id == session_id).order_by(Order.created_at.desc())
        )
        orders = result.scalars().all()
        return {"orders": [self._order_to_dict(o) for o in orders]}

    async def update_status(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        status: str | None = None,
        payment_status: str | None = None,
        payment_intent_id: str | None = None,
        payment_method: str | None = None,
    ) -> dict:
        """Update order status and/or payment status."""
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            return {"error": "Order not found"}

        if status:
            order.status = status
        if payment_status:
            order.payment_status = payment_status
        if payment_intent_id:
            order.payment_intent_id = payment_intent_id
        if payment_method:
            order.payment_method = payment_method
        order.updated_at = datetime.utcnow()

        await db.commit()
        return {"order": self._order_to_dict(order)}

    def _order_to_dict(self, order: Order) -> dict:
        """Convert Order model to API dict."""
        return {
            "id": str(order.id),
            "order_number": order.order_number,
            "customer_id": str(order.customer_id),
            "session_id": order.session_id,
            "shopper_email": order.shopper_email,
            "items": json.loads(order.items) if order.items else [],
            "subtotal": order.subtotal,
            "tax": order.tax,
            "shipping_cost": order.shipping_cost,
            "total": order.total,
            "currency": order.currency,
            "status": order.status,
            "payment_status": order.payment_status,
            "payment_intent_id": order.payment_intent_id,
            "payment_method": order.payment_method,
            "billing_address": json.loads(order.billing_address) if order.billing_address else None,
            "shipping_address": json.loads(order.shipping_address) if order.shipping_address else None,
            "notes": order.notes,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        }


# Singleton
_order_service: OrderService | None = None


def get_order_service() -> OrderService:
    global _order_service
    if _order_service is None:
        _order_service = OrderService()
    return _order_service
