"""
Webhook endpoints — Stripe payment confirmations.
"""
import logging
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.payment import get_payment_service

logger = logging.getLogger("zunkiree.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Handle Stripe webhook events.
    Accepts raw body for signature verification.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    payment_service = get_payment_service()
    result = await payment_service.handle_webhook(db, payload, sig_header)

    if "error" in result:
        logger.warning("Webhook error: %s", result["error"])
        return {"status": "error", "message": result["error"]}

    return result
