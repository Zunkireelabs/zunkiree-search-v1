"""
Stripe payment service — Checkout Sessions for redirect-based payments.
"""
import json
import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.order import Order
from app.config import get_settings

logger = logging.getLogger("zunkiree.payment")
settings = get_settings()


class PaymentService:
    def __init__(self):
        self._stripe = None

    def _get_stripe(self):
        if self._stripe is None:
            import stripe
            stripe.api_key = settings.stripe_secret_key
            self._stripe = stripe
        return self._stripe

    async def create_checkout_session(
        self,
        db: AsyncSession,
        order_id: uuid.UUID,
        success_url: str,
        cancel_url: str,
        stripe_account_id: str | None = None,
    ) -> dict:
        """Create a Stripe Checkout Session for an order."""
        result = await db.execute(select(Order).where(Order.id == order_id))
        order = result.scalar_one_or_none()
        if not order:
            return {"error": "Order not found"}

        if order.payment_status == "paid":
            return {"error": "Order is already paid"}

        items = json.loads(order.items) if order.items else []
        if not items:
            return {"error": "Order has no items"}

        stripe = self._get_stripe()

        # Build line items for Stripe
        line_items = []
        for item in items:
            desc_parts = []
            if item.get("size"):
                desc_parts.append(f"Size: {item['size']}")
            if item.get("color"):
                desc_parts.append(f"Color: {item['color']}")

            line_items.append({
                "price_data": {
                    "currency": (order.currency or "usd").lower(),
                    "product_data": {
                        "name": item["name"],
                        "description": ", ".join(desc_parts) if desc_parts else None,
                        "images": [item["image"]] if item.get("image") else None,
                    },
                    "unit_amount": int(item["price"] * 100),  # Stripe uses cents
                },
                "quantity": item.get("quantity", 1),
            })

        # Clean up None values in product_data
        for li in line_items:
            pd = li["price_data"]["product_data"]
            if pd.get("description") is None:
                del pd["description"]
            if pd.get("images") is None:
                del pd["images"]

        try:
            session_params = {
                "payment_method_types": ["card"],
                "line_items": line_items,
                "mode": "payment",
                "success_url": success_url + "?session_id={CHECKOUT_SESSION_ID}",
                "cancel_url": cancel_url,
                "metadata": {
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                },
            }

            if order.shopper_email:
                session_params["customer_email"] = order.shopper_email

            # Stripe Connect: charge on connected account
            if stripe_account_id:
                session_params["stripe_account"] = stripe_account_id

            checkout_session = stripe.checkout.Session.create(**session_params)

            # Update order with payment pending status
            order.status = "payment_pending"
            order.payment_intent_id = checkout_session.payment_intent or checkout_session.id
            order.payment_method = "stripe"
            await db.commit()

            return {
                "checkout_url": checkout_session.url,
                "session_id": checkout_session.id,
            }
        except Exception as e:
            logger.exception("Stripe checkout session creation failed: %s", e)
            return {"error": f"Payment setup failed: {str(e)}"}

    async def handle_webhook(
        self,
        db: AsyncSession,
        payload: bytes,
        sig_header: str,
    ) -> dict:
        """Handle Stripe webhook events."""
        stripe = self._get_stripe()

        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.stripe_webhook_secret
            )
        except ValueError:
            return {"error": "Invalid payload"}
        except stripe.error.SignatureVerificationError:
            return {"error": "Invalid signature"}

        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            order_id = session.get("metadata", {}).get("order_id")
            if order_id:
                result = await db.execute(
                    select(Order).where(Order.id == uuid.UUID(order_id))
                )
                order = result.scalar_one_or_none()
                if order:
                    order.status = "paid"
                    order.payment_status = "paid"
                    order.payment_intent_id = session.get("payment_intent", order.payment_intent_id)
                    await db.commit()
                    logger.info("Order %s marked as paid", order.order_number)

        elif event["type"] == "checkout.session.expired":
            session = event["data"]["object"]
            order_id = session.get("metadata", {}).get("order_id")
            if order_id:
                result = await db.execute(
                    select(Order).where(Order.id == uuid.UUID(order_id))
                )
                order = result.scalar_one_or_none()
                if order and order.payment_status != "paid":
                    order.status = "pending"
                    order.payment_status = "unpaid"
                    await db.commit()

        return {"status": "ok"}


# Singleton
_payment_service: PaymentService | None = None


def get_payment_service() -> PaymentService:
    global _payment_service
    if _payment_service is None:
        _payment_service = PaymentService()
    return _payment_service
