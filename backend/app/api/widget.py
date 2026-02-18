import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import Customer, WidgetConfig

router = APIRouter(prefix="/widget", tags=["widget"])


class WidgetConfigResponse(BaseModel):
    brand_name: str
    primary_color: str
    tone: str
    placeholder_text: str
    welcome_message: str | None
    show_sources: bool
    show_suggestions: bool
    quick_actions: list[str] = []


@router.get("/config/{site_id}", response_model=WidgetConfigResponse)
async def get_widget_config(
    site_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get widget configuration for a site.

    This endpoint is called by the widget on initialization
    to retrieve branding and behavior settings.
    """
    # Get customer
    result = await db.execute(
        select(Customer).where(
            Customer.site_id == site_id,
            Customer.is_active == True,
        )
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=404,
            detail={"code": "INVALID_SITE_ID", "message": "Site not found"},
        )

    # Get widget config
    result = await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
    )
    config = result.scalar_one_or_none()

    if not config:
        # Return defaults if no config exists
        return WidgetConfigResponse(
            brand_name=customer.name,
            primary_color="#2563eb",
            tone="neutral",
            placeholder_text="Ask a question...",
            welcome_message=None,
            show_sources=True,
            show_suggestions=True,
            quick_actions=[],
        )

    # Parse quick_actions from JSON string
    quick_actions: list[str] = []
    if config.quick_actions:
        try:
            quick_actions = json.loads(config.quick_actions)
        except (json.JSONDecodeError, TypeError):
            quick_actions = []

    return WidgetConfigResponse(
        brand_name=config.brand_name,
        primary_color=config.primary_color,
        tone=config.tone,
        placeholder_text=config.placeholder_text,
        welcome_message=config.welcome_message,
        show_sources=config.show_sources,
        show_suggestions=config.show_suggestions,
        quick_actions=quick_actions,
    )
