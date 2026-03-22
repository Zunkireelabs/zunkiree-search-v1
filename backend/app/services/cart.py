"""
Shopping cart service — in-memory with async DB write-through.
"""
import json
import uuid
import logging
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.cart import ShoppingCart

logger = logging.getLogger("zunkiree.cart")


@dataclass
class CartItem:
    product_id: str
    name: str
    price: float
    currency: str
    quantity: int = 1
    size: str = ""
    color: str = ""
    image: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "price": self.price,
            "currency": self.currency,
            "quantity": self.quantity,
            "size": self.size,
            "color": self.color,
            "image": self.image,
            "url": self.url,
        }


@dataclass
class CartState:
    items: list[CartItem] = field(default_factory=list)
    item_count: int = 0
    subtotal: float = 0.0
    currency: str = ""

    def to_dict(self) -> dict:
        return {
            "items": [item.to_dict() for item in self.items],
            "item_count": self.item_count,
            "subtotal": round(self.subtotal, 2),
            "currency": self.currency,
        }


class CartService:
    def __init__(self):
        self._carts: dict[str, CartState] = {}

    def get_cart(self, session_id: str) -> CartState:
        """Get cart for a session (in-memory only — use async get_cart_with_db for DB fallback)."""
        if session_id not in self._carts:
            self._carts[session_id] = CartState()
        return self._carts[session_id]

    async def load_from_db(self, db: AsyncSession, session_id: str) -> CartState:
        """Load cart from DB if not in memory. Called once when a returning session is seen."""
        if session_id in self._carts and self._carts[session_id].items:
            return self._carts[session_id]
        result = await db.execute(
            select(ShoppingCart).where(ShoppingCart.session_id == session_id)
        )
        db_cart = result.scalar_one_or_none()
        if db_cart and db_cart.items:
            items_data = json.loads(db_cart.items)
            cart = CartState()
            for item in items_data:
                cart.items.append(CartItem(
                    product_id=item.get("product_id", ""),
                    name=item.get("name", ""),
                    price=item.get("price", 0),
                    currency=item.get("currency", ""),
                    quantity=item.get("quantity", 1),
                    size=item.get("size", ""),
                    color=item.get("color", ""),
                    image=item.get("image", ""),
                    url=item.get("url", ""),
                ))
            self._recalculate(cart)
            self._carts[session_id] = cart
            return cart
        return self.get_cart(session_id)

    def add_item(
        self,
        session_id: str,
        product_id: str,
        name: str,
        price: float,
        currency: str,
        quantity: int = 1,
        size: str = "",
        color: str = "",
        image: str = "",
        url: str = "",
    ) -> CartState:
        """Add an item to the cart."""
        cart = self.get_cart(session_id)

        # Check if item already exists (same product + size + color)
        for item in cart.items:
            if item.product_id == product_id and item.size == size and item.color == color:
                item.quantity += quantity
                self._recalculate(cart)
                return cart

        cart.items.append(CartItem(
            product_id=product_id,
            name=name,
            price=price,
            currency=currency,
            quantity=quantity,
            size=size,
            color=color,
            image=image,
            url=url,
        ))
        self._recalculate(cart)
        return cart

    def remove_item(self, session_id: str, index: int) -> CartState:
        """Remove item at index from cart."""
        cart = self.get_cart(session_id)
        if 0 <= index < len(cart.items):
            cart.items.pop(index)
        self._recalculate(cart)
        return cart

    def clear_cart(self, session_id: str) -> CartState:
        """Clear all items from cart."""
        self._carts[session_id] = CartState()
        return self._carts[session_id]

    def _recalculate(self, cart: CartState) -> None:
        """Recalculate cart totals."""
        cart.item_count = sum(item.quantity for item in cart.items)
        cart.subtotal = sum(item.price * item.quantity for item in cart.items)
        if cart.items:
            cart.currency = cart.items[0].currency

    async def save_to_db(self, db: AsyncSession, session_id: str, customer_id: uuid.UUID) -> None:
        """Write-through: persist cart state to database."""
        cart = self.get_cart(session_id)
        result = await db.execute(
            select(ShoppingCart).where(ShoppingCart.session_id == session_id)
        )
        db_cart = result.scalar_one_or_none()

        items_json = json.dumps([item.to_dict() for item in cart.items])

        if db_cart:
            db_cart.items = items_json
        else:
            db_cart = ShoppingCart(
                session_id=session_id,
                customer_id=customer_id,
                items=items_json,
            )
            db.add(db_cart)

        await db.commit()


# Singleton
_cart_service: CartService | None = None


def get_cart_service() -> CartService:
    global _cart_service
    if _cart_service is None:
        _cart_service = CartService()
    return _cart_service
