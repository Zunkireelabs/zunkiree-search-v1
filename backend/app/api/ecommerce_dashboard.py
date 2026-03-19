"""
Ecommerce dashboard API endpoints — orders, products, analytics for merchants.
Authenticated via x-api-key header.
"""
import json
import csv
import io
import logging
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, desc

from app.database import get_db
from app.models import Customer, Product, WidgetConfig
from app.models.order import Order

logger = logging.getLogger("zunkiree.ecommerce_dashboard")

router = APIRouter(prefix="/ecommerce", tags=["ecommerce-dashboard"])


async def _authenticate(db: AsyncSession, api_key: str) -> Customer:
    """Authenticate merchant by API key."""
    result = await db.execute(
        select(Customer).where(Customer.api_key == api_key, Customer.is_active == True)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return customer


# ===== Orders =====

@router.get("/orders")
async def list_orders(
    x_api_key: str = Header(...),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List orders with pagination and optional status filter."""
    customer = await _authenticate(db, x_api_key)

    query = select(Order).where(Order.customer_id == customer.id)
    count_query = select(func.count()).select_from(Order).where(Order.customer_id == customer.id)

    if status:
        query = query.where(Order.status == status)
        count_query = count_query.where(Order.status == status)

    # Count total
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(desc(Order.created_at)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    orders = result.scalars().all()

    return {
        "orders": [_order_to_dict(o) for o in orders],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/orders/{order_id}")
async def get_order_detail(
    order_id: uuid.UUID,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Get full order detail."""
    customer = await _authenticate(db, x_api_key)

    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.customer_id == customer.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return {"order": _order_to_dict(order)}


class UpdateStatusRequest(BaseModel):
    status: str


@router.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: uuid.UUID,
    body: UpdateStatusRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Update order status (processing, shipped, delivered, cancelled)."""
    customer = await _authenticate(db, x_api_key)

    valid_statuses = {"pending", "processing", "shipped", "delivered", "cancelled", "refunded"}
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.customer_id == customer.id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = body.status
    order.updated_at = datetime.utcnow()
    await db.commit()

    return {"order": _order_to_dict(order)}


@router.get("/orders/export")
async def export_orders(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Export all orders as CSV."""
    customer = await _authenticate(db, x_api_key)

    result = await db.execute(
        select(Order).where(Order.customer_id == customer.id).order_by(desc(Order.created_at))
    )
    orders = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["order_number", "status", "payment_status", "total", "currency", "shopper_email", "created_at"])
    for o in orders:
        writer.writerow([o.order_number, o.status, o.payment_status, o.total, o.currency, o.shopper_email or "", o.created_at.isoformat() if o.created_at else ""])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=orders.csv"},
    )


# ===== Products =====

@router.get("/products")
async def list_products(
    x_api_key: str = Header(...),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List products with pagination and search."""
    customer = await _authenticate(db, x_api_key)

    query = select(Product).where(Product.customer_id == customer.id)
    count_query = select(func.count()).select_from(Product).where(Product.customer_id == customer.id)

    if search:
        search_filter = Product.name.ilike(f"%{search}%")
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(desc(Product.updated_at)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    products = result.scalars().all()

    return {
        "products": [_product_to_dict(p) for p in products],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


class UpdateProductRequest(BaseModel):
    price: float | None = None
    in_stock: bool | None = None
    description: str | None = None


@router.put("/products/{product_id}")
async def update_product(
    product_id: uuid.UUID,
    body: UpdateProductRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Update product price, stock status, or description."""
    customer = await _authenticate(db, x_api_key)

    result = await db.execute(
        select(Product).where(Product.id == product_id, Product.customer_id == customer.id)
    )
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if body.price is not None:
        product.price = body.price
    if body.in_stock is not None:
        product.in_stock = body.in_stock
    if body.description is not None:
        product.description = body.description
    product.updated_at = datetime.utcnow()
    await db.commit()

    return {"product": _product_to_dict(product)}


@router.get("/products/stats")
async def product_stats(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Get product statistics."""
    customer = await _authenticate(db, x_api_key)

    total_result = await db.execute(
        select(func.count()).select_from(Product).where(Product.customer_id == customer.id)
    )
    total = total_result.scalar() or 0

    oos_result = await db.execute(
        select(func.count()).select_from(Product).where(
            Product.customer_id == customer.id, Product.in_stock == False
        )
    )
    out_of_stock = oos_result.scalar() or 0

    price_result = await db.execute(
        select(func.min(Product.price), func.max(Product.price), func.avg(Product.price)).where(
            Product.customer_id == customer.id, Product.price.isnot(None)
        )
    )
    price_row = price_result.one_or_none()

    category_result = await db.execute(
        select(Product.category, func.count()).where(
            Product.customer_id == customer.id, Product.category.isnot(None)
        ).group_by(Product.category)
    )
    categories = {row[0]: row[1] for row in category_result.fetchall() if row[0]}

    return {
        "total": total,
        "out_of_stock": out_of_stock,
        "in_stock": total - out_of_stock,
        "price_range": {
            "min": price_row[0] if price_row else None,
            "max": price_row[1] if price_row else None,
            "avg": round(price_row[2], 2) if price_row and price_row[2] else None,
        },
        "categories": categories,
    }


# ===== Analytics =====

@router.get("/analytics/overview")
async def analytics_overview(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Get overview KPIs: revenue, order count, avg order value, pending orders."""
    customer = await _authenticate(db, x_api_key)

    # Total revenue (paid orders)
    rev_result = await db.execute(
        select(func.sum(Order.total), func.count()).where(
            Order.customer_id == customer.id, Order.payment_status == "paid"
        )
    )
    rev_row = rev_result.one_or_none()
    total_revenue = rev_row[0] or 0 if rev_row else 0
    paid_orders = rev_row[1] or 0 if rev_row else 0

    # Total orders
    total_result = await db.execute(
        select(func.count()).select_from(Order).where(Order.customer_id == customer.id)
    )
    total_orders = total_result.scalar() or 0

    # Pending orders
    pending_result = await db.execute(
        select(func.count()).select_from(Order).where(
            Order.customer_id == customer.id, Order.status.in_(["pending", "payment_pending"])
        )
    )
    pending_orders = pending_result.scalar() or 0

    avg_order_value = round(total_revenue / paid_orders, 2) if paid_orders > 0 else 0

    return {
        "total_revenue": round(total_revenue, 2),
        "total_orders": total_orders,
        "paid_orders": paid_orders,
        "pending_orders": pending_orders,
        "avg_order_value": avg_order_value,
    }


@router.get("/analytics/revenue")
async def analytics_revenue(
    x_api_key: str = Header(...),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Daily revenue over the last N days."""
    customer = await _authenticate(db, x_api_key)
    since = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        text("""
            SELECT DATE(created_at) as day, SUM(total) as revenue, COUNT(*) as orders
            FROM orders
            WHERE customer_id = :cid AND payment_status = 'paid' AND created_at >= :since
            GROUP BY DATE(created_at)
            ORDER BY day
        """),
        {"cid": str(customer.id), "since": since},
    )

    data = []
    for row in result.fetchall():
        data.append({
            "date": row[0].isoformat() if row[0] else None,
            "revenue": round(row[1], 2) if row[1] else 0,
            "orders": row[2],
        })

    return {"data": data, "days": days}


@router.get("/analytics/top-products")
async def analytics_top_products(
    x_api_key: str = Header(...),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Top products by revenue from paid orders."""
    customer = await _authenticate(db, x_api_key)

    # Get all paid orders and aggregate by product
    result = await db.execute(
        select(Order.items).where(
            Order.customer_id == customer.id, Order.payment_status == "paid"
        )
    )

    product_revenue: dict[str, dict] = {}
    for row in result.fetchall():
        items = json.loads(row[0]) if row[0] else []
        for item in items:
            pid = item.get("product_id", item.get("name", "unknown"))
            if pid not in product_revenue:
                product_revenue[pid] = {
                    "name": item.get("name", "Unknown"),
                    "revenue": 0,
                    "units_sold": 0,
                }
            qty = item.get("quantity", 1)
            product_revenue[pid]["revenue"] += item.get("price", 0) * qty
            product_revenue[pid]["units_sold"] += qty

    # Sort and limit
    sorted_products = sorted(product_revenue.values(), key=lambda x: x["revenue"], reverse=True)[:limit]
    for p in sorted_products:
        p["revenue"] = round(p["revenue"], 2)

    return {"products": sorted_products}


# ===== Settings =====

class SettingsUpdateRequest(BaseModel):
    stripe_account_id: str | None = None
    payment_enabled: bool | None = None
    checkout_mode: str | None = None
    shipping_countries: list[str] | None = None


@router.put("/settings")
async def update_settings(
    body: SettingsUpdateRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Update ecommerce settings."""
    customer = await _authenticate(db, x_api_key)

    result = await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Widget config not found")

    if body.stripe_account_id is not None:
        config.stripe_account_id = body.stripe_account_id
    if body.payment_enabled is not None:
        config.payment_enabled = body.payment_enabled
    if body.checkout_mode is not None:
        config.checkout_mode = body.checkout_mode
    if body.shipping_countries is not None:
        config.shipping_countries = json.dumps(body.shipping_countries)

    await db.commit()

    return {
        "stripe_account_id": config.stripe_account_id,
        "payment_enabled": config.payment_enabled,
        "checkout_mode": config.checkout_mode,
        "shipping_countries": json.loads(config.shipping_countries) if config.shipping_countries else [],
    }


@router.get("/settings")
async def get_settings(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Get current ecommerce settings."""
    customer = await _authenticate(db, x_api_key)

    result = await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="Widget config not found")

    return {
        "stripe_account_id": config.stripe_account_id,
        "payment_enabled": config.payment_enabled,
        "checkout_mode": config.checkout_mode,
        "shipping_countries": json.loads(config.shipping_countries) if config.shipping_countries else [],
        "enable_shopping": config.enable_shopping,
    }


# ===== Helpers =====

def _order_to_dict(order: Order) -> dict:
    return {
        "id": str(order.id),
        "order_number": order.order_number,
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


def _product_to_dict(p: Product) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "sku": p.sku,
        "brand": p.brand,
        "category": p.category,
        "price": p.price,
        "currency": p.currency,
        "original_price": p.original_price,
        "images": json.loads(p.images) if p.images else [],
        "url": p.url,
        "sizes": json.loads(p.sizes) if p.sizes else [],
        "colors": json.loads(p.colors) if p.colors else [],
        "in_stock": p.in_stock,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
