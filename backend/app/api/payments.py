"""
Payment API endpoints — eSewa and Khalti payment initiation, status polling, and callbacks.
"""
import json
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.order import Order
from app.models.payment import Payment
from app.services import esewa, khalti

logger = logging.getLogger("zunkiree.payments.api")

router = APIRouter(prefix="/payments", tags=["payments"])

# HTML page that closes the popup and shows a brief status message
CALLBACK_HTML = """<!DOCTYPE html>
<html><head><title>Payment {status}</title></head>
<body style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif">
<div style="text-align:center">
<p style="font-size:18px">{message}</p>
<p style="color:#888">This window will close automatically...</p>
</div>
<script>setTimeout(function(){{ window.close() }}, 1500)</script>
</body></html>"""


class InitiateRequest(BaseModel):
    order_id: str = Field(..., description="Order UUID")
    gateway: str = Field(..., pattern="^(esewa|khalti)$", description="Payment gateway")
    site_id: str = Field(..., description="Site identifier")


class PaymentStatusResponse(BaseModel):
    status: str
    gateway: str
    transaction_id: str | None = None


@router.post("/initiate")
async def initiate_payment(
    body: InitiateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Initiate an eSewa or Khalti payment for an order."""
    # Get order
    try:
        order_uuid = uuid.UUID(body.order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid order_id")

    result = await db.execute(select(Order).where(Order.id == order_uuid))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.payment_status == "paid":
        raise HTTPException(status_code=400, detail="Order is already paid")

    # Create payment record
    payment = Payment(
        order_id=order.id,
        customer_id=order.customer_id,
        gateway=body.gateway,
        amount=order.total,
        currency=order.currency or "NPR",
        status="pending",
        gateway_ref=str(uuid.uuid4()),  # placeholder, updated below
    )
    db.add(payment)
    await db.flush()  # get payment.id

    # Build callback base URL from the request
    base = str(request.base_url).rstrip("/")

    if body.gateway == "esewa":
        payment.gateway_ref = str(payment.id)  # use payment ID as transaction_uuid
        success_url = f"{base}/api/v1/payments/esewa/callback"
        failure_url = f"{base}/api/v1/payments/esewa/callback?failed=1&payment_id={payment.id}"

        esewa_data = esewa.build_payment_form(
            total_amount=order.total,
            transaction_uuid=str(payment.id),
            success_url=success_url,
            failure_url=failure_url,
        )

        order.status = "payment_pending"
        order.payment_method = "esewa"
        await db.commit()

        return {
            "paymentId": str(payment.id),
            "paymentUrl": esewa_data["payment_url"],
            "formData": esewa_data["form_data"],
        }

    elif body.gateway == "khalti":
        return_url = f"{base}/api/v1/payments/khalti/callback?payment_id={payment.id}"

        khalti_result = await khalti.initiate_payment(
            amount_npr=order.total,
            purchase_order_id=str(order.id),
            purchase_order_name=order.order_number,
            return_url=return_url,
        )

        if "error" in khalti_result:
            await db.rollback()
            raise HTTPException(status_code=502, detail=khalti_result["error"])

        payment.gateway_ref = khalti_result["pidx"]
        order.status = "payment_pending"
        order.payment_method = "khalti"
        await db.commit()

        return {
            "paymentId": str(payment.id),
            "paymentUrl": khalti_result["payment_url"],
        }


@router.get("/{payment_id}/status")
async def get_payment_status(
    payment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Poll payment status."""
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    return PaymentStatusResponse(
        status=payment.status,
        gateway=payment.gateway,
        transaction_id=payment.transaction_id,
    )


@router.get("/esewa/callback", response_class=HTMLResponse)
async def esewa_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle eSewa redirect after payment."""
    params = dict(request.query_params)

    # Failure redirect
    if params.get("failed"):
        payment_id = params.get("payment_id")
        if payment_id:
            try:
                result = await db.execute(
                    select(Payment).where(Payment.id == uuid.UUID(payment_id))
                )
                payment = result.scalar_one_or_none()
                if payment and payment.status == "pending":
                    payment.status = "failed"
                    payment.updated_at = datetime.utcnow()
                    await db.commit()
            except Exception:
                pass
        return HTMLResponse(CALLBACK_HTML.format(status="Failed", message="Payment was not completed."))

    # Success redirect — eSewa sends base64 data
    encoded_data = params.get("data")
    if not encoded_data:
        return HTMLResponse(CALLBACK_HTML.format(status="Error", message="No payment data received."))

    data = esewa.verify_callback(encoded_data)
    if not data:
        return HTMLResponse(CALLBACK_HTML.format(status="Error", message="Payment verification failed."))

    transaction_uuid = data.get("transaction_uuid")
    if not transaction_uuid:
        return HTMLResponse(CALLBACK_HTML.format(status="Error", message="Missing transaction reference."))

    # Find payment by gateway_ref (transaction_uuid = payment.id)
    try:
        result = await db.execute(
            select(Payment).where(Payment.gateway_ref == transaction_uuid)
        )
        payment = result.scalar_one_or_none()
    except Exception:
        payment = None

    if not payment:
        return HTMLResponse(CALLBACK_HTML.format(status="Error", message="Payment record not found."))

    if payment.status == "completed":
        return HTMLResponse(CALLBACK_HTML.format(status="Complete", message="Payment already confirmed!"))

    # Mark payment as completed
    payment.status = "completed"
    payment.transaction_id = data.get("transaction_code")
    payment.gateway_response = json.dumps(data)
    payment.updated_at = datetime.utcnow()

    # Update order
    order_result = await db.execute(select(Order).where(Order.id == payment.order_id))
    order = order_result.scalar_one_or_none()
    if order:
        order.status = "paid"
        order.payment_status = "paid"
        order.payment_intent_id = data.get("transaction_code")

    await db.commit()
    logger.info("eSewa payment completed: payment=%s order=%s", payment.id, payment.order_id)

    return HTMLResponse(CALLBACK_HTML.format(status="Complete", message="Payment successful! Thank you."))


@router.get("/khalti/callback", response_class=HTMLResponse)
async def khalti_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Khalti redirect after payment."""
    params = dict(request.query_params)
    payment_id = params.get("payment_id")
    pidx = params.get("pidx")

    if not payment_id:
        return HTMLResponse(CALLBACK_HTML.format(status="Error", message="Missing payment reference."))

    try:
        result = await db.execute(
            select(Payment).where(Payment.id == uuid.UUID(payment_id))
        )
        payment = result.scalar_one_or_none()
    except Exception:
        payment = None

    if not payment:
        return HTMLResponse(CALLBACK_HTML.format(status="Error", message="Payment record not found."))

    if payment.status == "completed":
        return HTMLResponse(CALLBACK_HTML.format(status="Complete", message="Payment already confirmed!"))

    # Verify with Khalti lookup API
    lookup_pidx = pidx or payment.gateway_ref
    if not lookup_pidx:
        return HTMLResponse(CALLBACK_HTML.format(status="Error", message="Missing payment identifier."))

    lookup_result = await khalti.lookup_payment(lookup_pidx)

    if "error" in lookup_result:
        payment.status = "failed"
        payment.gateway_response = json.dumps(lookup_result)
        payment.updated_at = datetime.utcnow()
        await db.commit()
        return HTMLResponse(CALLBACK_HTML.format(status="Failed", message="Payment verification failed."))

    khalti_status = lookup_result.get("status", "").lower()

    if khalti_status == "completed":
        payment.status = "completed"
        payment.transaction_id = lookup_result.get("transaction_id")
        payment.gateway_response = json.dumps(lookup_result)
        payment.updated_at = datetime.utcnow()

        # Update order
        order_result = await db.execute(select(Order).where(Order.id == payment.order_id))
        order = order_result.scalar_one_or_none()
        if order:
            order.status = "paid"
            order.payment_status = "paid"
            order.payment_intent_id = lookup_result.get("transaction_id")

        await db.commit()
        logger.info("Khalti payment completed: payment=%s order=%s", payment.id, payment.order_id)
        return HTMLResponse(CALLBACK_HTML.format(status="Complete", message="Payment successful! Thank you."))
    else:
        payment.status = "failed"
        payment.gateway_response = json.dumps(lookup_result)
        payment.updated_at = datetime.utcnow()
        await db.commit()
        return HTMLResponse(CALLBACK_HTML.format(status="Failed", message="Payment was not completed."))
