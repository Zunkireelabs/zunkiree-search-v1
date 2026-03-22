"""
OpenAI function-calling tool definitions and executors for ecommerce agent.
"""
import json
import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.product import Product
from app.models.widget_config import WidgetConfig
from app.services.cart import get_cart_service
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service
from app.services.wishlist import get_wishlist_service
from app.services.order import get_order_service

logger = logging.getLogger("zunkiree.tools")

# OpenAI function-calling tool definitions
ECOMMERCE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "product_search",
            "description": "Search for products by query. Use this when the user is looking for products, items, clothing, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query describing the product the user wants",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional product category filter",
                    },
                    "min_price": {
                        "type": "number",
                        "description": "Minimum price filter",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Maximum price filter",
                    },
                    "color": {
                        "type": "string",
                        "description": "Color filter",
                    },
                    "size": {
                        "type": "string",
                        "description": "Size filter",
                    },
                    "in_stock_only": {
                        "type": "boolean",
                        "description": "Only show in-stock products",
                        "default": True,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_cart",
            "description": "Add a product to the shopping cart. IMPORTANT: You MUST confirm the size with the customer before calling this tool if the product has sizes available. Ask for their size or body measurements first, then call with the confirmed size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product ID to add",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Number of items to add",
                        "default": 1,
                    },
                    "size": {
                        "type": "string",
                        "description": "The confirmed size (e.g. S, M, L, XL). Must be confirmed with the customer before adding.",
                    },
                    "color": {
                        "type": "string",
                        "description": "Selected color",
                    },
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cart",
            "description": "Get the current shopping cart contents. Use when user asks about their cart.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_cart",
            "description": "Remove an item from the shopping cart.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_index": {
                        "type": "integer",
                        "description": "Index of the item to remove (0-based)",
                    },
                },
                "required": ["item_index"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "checkout",
            "description": "Proceed to checkout. Initiates the checkout process for the current cart.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_wishlist",
            "description": "Add a product to the user's wishlist. Use when the user wants to save a product for later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product ID to add to wishlist",
                    },
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_from_wishlist",
            "description": "Remove a product from the user's wishlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "string",
                        "description": "The product ID to remove from wishlist",
                    },
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_wishlist",
            "description": "Get the user's wishlist contents. Use when user asks about saved or wishlisted items.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "Check the status of an order by order number. Use when a user asks about their order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {
                        "type": "string",
                        "description": "The order number (e.g. ZK-ABC123-0001)",
                    },
                },
                "required": ["order_number"],
            },
        },
    },
]


async def execute_tool(
    tool_name: str,
    tool_args: dict,
    db: AsyncSession,
    session_id: str,
    customer_id: uuid.UUID,
    site_id: str,
) -> dict:
    """Execute a tool and return the result."""
    if tool_name == "product_search":
        return await _product_search(db, customer_id, site_id, **tool_args)
    elif tool_name == "add_to_cart":
        return await _add_to_cart(db, session_id, customer_id, **tool_args)
    elif tool_name == "get_cart":
        return await _get_cart(db, session_id)
    elif tool_name == "remove_from_cart":
        return await _remove_from_cart(db, session_id, customer_id, **tool_args)
    elif tool_name == "checkout":
        return await _checkout(db, session_id, customer_id)
    elif tool_name == "add_to_wishlist":
        return await _add_to_wishlist(db, session_id, customer_id, **tool_args)
    elif tool_name == "remove_from_wishlist":
        return await _remove_from_wishlist(db, session_id, **tool_args)
    elif tool_name == "get_wishlist":
        return await _get_wishlist(db, session_id)
    elif tool_name == "get_order_status":
        return await _get_order_status(db, **tool_args)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


async def _product_search(
    db: AsyncSession,
    customer_id: uuid.UUID,
    site_id: str,
    query: str,
    category: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
    color: str = "",
    size: str = "",
    in_stock_only: bool = True,
) -> dict:
    """Search for products using vector search + metadata filtering."""
    embedding_service = get_embedding_service()
    vector_store = get_vector_store_service()

    # Generate embedding for the search query
    query_embedding = await embedding_service.create_embedding(query)

    # Search Pinecone with metadata filter for products
    matches = await vector_store.query_vectors(
        query_vector=query_embedding,
        namespace=site_id,
        top_k=10,
        site_id=site_id,
        filter_metadata={"type": "product"},
    )

    if not matches:
        return {"products": [], "message": "No products found matching your search."}

    # Track the best match score to indicate relevance
    best_score = max(m.get("score", 0) for m in matches)

    # Get product IDs from metadata
    product_ids = []
    for match in matches:
        pid = match.get("metadata", {}).get("product_id")
        if pid:
            product_ids.append(pid)

    if not product_ids:
        # Fallback: search products table directly
        return await _fallback_product_search(db, customer_id, query, min_price, max_price, in_stock_only)

    # Fetch full product data from database
    result = await db.execute(
        select(Product).where(
            Product.customer_id == customer_id,
            Product.id.in_([uuid.UUID(pid) for pid in product_ids]),
        )
    )
    products = result.scalars().all()

    # Apply filters
    filtered = []
    for p in products:
        if in_stock_only and not p.in_stock:
            continue
        if min_price is not None and p.price and p.price < min_price:
            continue
        if max_price is not None and p.price and p.price > max_price:
            continue
        if color:
            product_colors = json.loads(p.colors) if p.colors else []
            if not any(color.lower() in c.lower() for c in product_colors):
                continue
        if size:
            product_sizes = json.loads(p.sizes) if p.sizes else []
            if not any(size.upper() == s.upper() for s in product_sizes):
                continue

        filtered.append(_product_to_dict(p))

    result = {"products": filtered[:5], "best_match_score": round(best_score, 3)}
    if best_score < 0.45:
        result["note"] = "No exact matches found. These are the closest items we have."
    return result


async def _fallback_product_search(
    db: AsyncSession,
    customer_id: uuid.UUID,
    query: str,
    min_price: float | None = None,
    max_price: float | None = None,
    in_stock_only: bool = True,
) -> dict:
    """Fallback: search products by name/description in PostgreSQL."""
    from sqlalchemy import text

    sql = """
        SELECT id FROM products
        WHERE customer_id = :cid
        AND (LOWER(name) LIKE :q OR LOWER(description) LIKE :q OR LOWER(category) LIKE :q)
    """
    params: dict = {"cid": str(customer_id), "q": f"%{query.lower()}%"}

    if in_stock_only:
        sql += " AND in_stock = TRUE"
    if min_price is not None:
        sql += " AND price >= :min_price"
        params["min_price"] = min_price
    if max_price is not None:
        sql += " AND price <= :max_price"
        params["max_price"] = max_price

    sql += " LIMIT 5"

    result = await db.execute(text(sql), params)
    product_ids = [row[0] for row in result.fetchall()]

    if not product_ids:
        return {"products": [], "message": "No products found matching your search."}

    result = await db.execute(
        select(Product).where(Product.id.in_(product_ids))
    )
    products = result.scalars().all()

    return {"products": [_product_to_dict(p) for p in products[:5]]}


async def _add_to_cart(
    db: AsyncSession,
    session_id: str,
    customer_id: uuid.UUID,
    product_id: str,
    quantity: int = 1,
    size: str = "",
    color: str = "",
) -> dict:
    """Add a product to the cart."""
    # Validate product exists
    result = await db.execute(
        select(Product).where(
            Product.id == uuid.UUID(product_id),
            Product.customer_id == customer_id,
        )
    )
    product = result.scalar_one_or_none()

    if not product:
        return {"error": "Product not found"}

    if not product.in_stock:
        return {"error": f"{product.name} is currently out of stock"}

    images = json.loads(product.images) if product.images else []
    cart_service = get_cart_service()
    cart = cart_service.add_item(
        session_id=session_id,
        product_id=product_id,
        name=product.name,
        price=product.price or 0,
        currency=product.currency or "",
        quantity=quantity,
        size=size,
        color=color,
        image=images[0] if images else "",
        url=product.url or "",
    )

    await cart_service.save_to_db(db, session_id, customer_id)

    return {"cart": cart.to_dict(), "message": f"Added {product.name} to your cart!"}


async def _get_cart(db: AsyncSession, session_id: str) -> dict:
    """Get current cart contents."""
    cart_service = get_cart_service()
    cart = cart_service.get_cart(session_id)
    return {"cart": cart.to_dict()}


async def _remove_from_cart(db: AsyncSession, session_id: str, customer_id: uuid.UUID, item_index: int = 0) -> dict:
    """Remove item from cart."""
    cart_service = get_cart_service()
    cart = cart_service.remove_item(session_id, item_index)
    await cart_service.save_to_db(db, session_id, customer_id)
    return {"cart": cart.to_dict(), "message": "Item removed from cart."}


async def _checkout(db: AsyncSession, session_id: str, customer_id: uuid.UUID) -> dict:
    """Handle checkout based on merchant's checkout_mode setting."""
    cart_service = get_cart_service()
    cart = cart_service.get_cart(session_id)

    if not cart.items:
        return {"error": "Your cart is empty."}

    # Check checkout mode from widget config
    config_result = await db.execute(
        select(WidgetConfig).where(WidgetConfig.customer_id == customer_id)
    )
    config = config_result.scalar_one_or_none()
    checkout_mode = config.checkout_mode if config else "redirect"

    checkout_items = []
    for item in cart.items:
        checkout_items.append({
            "name": item.name,
            "price": item.price,
            "currency": item.currency,
            "quantity": item.quantity,
            "size": item.size,
            "color": item.color,
            "url": item.url,
            "image": item.image,
        })

    if checkout_mode == "in-app":
        # In-app checkout: signal that address form is needed
        return {
            "address_form_required": True,
            "checkout": {
                "items": checkout_items,
                "subtotal": round(cart.subtotal, 2),
                "currency": cart.currency,
                "item_count": cart.item_count,
                "checkout_mode": "in-app",
            },
        }

    # Default: redirect checkout
    return {
        "checkout": {
            "items": checkout_items,
            "subtotal": round(cart.subtotal, 2),
            "currency": cart.currency,
            "item_count": cart.item_count,
            "checkout_mode": "redirect",
        }
    }


# ===== Wishlist tools =====

async def _add_to_wishlist(db: AsyncSession, session_id: str, customer_id: uuid.UUID, product_id: str) -> dict:
    """Add a product to the wishlist."""
    service = get_wishlist_service()
    return await service.add_to_wishlist(db, session_id, customer_id, product_id)


async def _remove_from_wishlist(db: AsyncSession, session_id: str, product_id: str) -> dict:
    """Remove a product from the wishlist."""
    service = get_wishlist_service()
    return await service.remove_from_wishlist(db, session_id, product_id)


async def _get_wishlist(db: AsyncSession, session_id: str) -> dict:
    """Get wishlist contents."""
    service = get_wishlist_service()
    return await service.get_wishlist(db, session_id)


# ===== Order tools =====

async def _get_order_status(db: AsyncSession, order_number: str) -> dict:
    """Get order status by order number."""
    service = get_order_service()
    return await service.get_order_by_number(db, order_number)


def _product_to_dict(p: Product) -> dict:
    """Convert Product model to API-friendly dict."""
    return {
        "id": str(p.id),
        "name": p.name,
        "description": (p.description or "")[:200],
        "price": p.price,
        "currency": p.currency or "",
        "original_price": p.original_price,
        "images": json.loads(p.images) if p.images else [],
        "url": p.url or "",
        "brand": p.brand or "",
        "category": p.category or "",
        "sizes": json.loads(p.sizes) if p.sizes else [],
        "colors": json.loads(p.colors) if p.colors else [],
        "in_stock": p.in_stock,
    }
