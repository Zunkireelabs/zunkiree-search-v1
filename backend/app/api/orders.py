"""
Order API endpoints — create orders from cart, get order details, initiate payment.
"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Customer, WidgetConfig
from app.services.order import get_order_service
from app.services.payment import get_payment_service

logger = logging.getLogger("zunkiree.orders.api")

router = APIRouter(prefix="/orders", tags=["orders"])


class AddressInput(BaseModel):
    full_name: str = Field(..., max_length=200)
    line1: str = Field(..., max_length=500)
    line2: str | None = Field(None, max_length=500)
    city: str = Field(..., max_length=200)
    state: str = Field(..., max_length=200)
    postal_code: str = Field(..., max_length=20)
    country: str = Field(..., max_length=2)
    phone: str | None = Field(None, max_length=30)


class CreateOrderRequest(BaseModel):
    site_id: str
    session_id: str
    billing_address: AddressInput
    shipping_address: AddressInput | None = None
    shopper_email: str | None = None
    notes: str | None = None
    same_as_billing: bool = True


class PayOrderRequest(BaseModel):
    success_url: str
    cancel_url: str


@router.post("/create")
async def create_order(
    request: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create an order from the current cart contents."""
    result = await db.execute(
        select(Customer).where(Customer.site_id == request.site_id, Customer.is_active == True)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    shipping = request.shipping_address
    if request.same_as_billing and shipping is None:
        shipping = request.billing_address

    order_service = get_order_service()
    result = await order_service.create_order_from_cart(
        db=db,
        session_id=request.session_id,
        customer_id=customer.id,
        billing_address=request.billing_address.model_dump() if request.billing_address else None,
        shipping_address=shipping.model_dump() if shipping else None,
        shopper_email=request.shopper_email,
        notes=request.notes,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.get("/{order_id}")
async def get_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get order details by ID."""
    order_service = get_order_service()
    result = await order_service.get_order(db, order_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/session/{session_id}")
async def get_session_orders(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all orders for a session."""
    order_service = get_order_service()
    return await order_service.get_session_orders(db, session_id)


@router.post("/{order_id}/pay")
async def pay_order(
    order_id: uuid.UUID,
    request: PayOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a Stripe Checkout Session for an order."""
    # Get order to find customer
    order_service = get_order_service()
    order_result = await order_service.get_order(db, order_id)
    if "error" in order_result:
        raise HTTPException(status_code=404, detail=order_result["error"])

    # Get stripe account ID from widget config
    customer_id = uuid.UUID(order_result["order"]["customer_id"])
    config_result = await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer_id)
    )
    config = config_result.scalar_one_or_none()
    stripe_account_id = getattr(config, "stripe_account_id", None) if config else None

    payment_service = get_payment_service()
    result = await payment_service.create_checkout_session(
        db=db,
        order_id=order_id,
        success_url=request.success_url,
        cancel_url=request.cancel_url,
        stripe_account_id=stripe_account_id,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result
