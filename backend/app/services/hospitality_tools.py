"""
OpenAI function-calling tool definitions and executors for hospitality agent.
"""
import json
import logging
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.room import Room
from app.models.user_profile import UserProfile

logger = logging.getLogger("zunkiree.hospitality_tools")

HOSPITALITY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_rooms",
            "description": "Search for available hotel rooms. Use when the user asks about rooms, accommodation, or availability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g. 'deluxe room', 'suite with balcony')",
                    },
                    "room_type": {
                        "type": "string",
                        "description": "Room type filter (standard, deluxe, suite, etc.)",
                    },
                    "min_price": {
                        "type": "number",
                        "description": "Minimum price per night",
                    },
                    "max_price": {
                        "type": "number",
                        "description": "Maximum price per night",
                    },
                    "guests": {
                        "type": "integer",
                        "description": "Number of guests",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "make_booking_inquiry",
            "description": "Create a booking inquiry for a room. Collect guest name, email, check-in/check-out dates, and number of guests before calling this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "room_id": {
                        "type": "string",
                        "description": "The room ID to book",
                    },
                    "guest_name": {
                        "type": "string",
                        "description": "Guest's full name",
                    },
                    "guest_email": {
                        "type": "string",
                        "description": "Guest's email address",
                    },
                    "check_in": {
                        "type": "string",
                        "description": "Check-in date (YYYY-MM-DD)",
                    },
                    "check_out": {
                        "type": "string",
                        "description": "Check-out date (YYYY-MM-DD)",
                    },
                    "guest_count": {
                        "type": "integer",
                        "description": "Number of guests",
                    },
                    "special_requests": {
                        "type": "string",
                        "description": "Any special requests from the guest",
                    },
                },
                "required": ["room_id", "guest_name", "guest_email", "check_in", "check_out", "guest_count"],
            },
        },
    },
]


async def execute_hospitality_tool(
    tool_name: str,
    tool_args: dict,
    db: AsyncSession,
    session_id: str,
    customer_id: uuid.UUID,
    site_id: str,
) -> dict:
    """Execute a hospitality tool and return the result."""
    if tool_name == "search_rooms":
        return await _search_rooms(db, customer_id, **tool_args)
    elif tool_name == "make_booking_inquiry":
        return await _make_booking_inquiry(db, customer_id, **tool_args)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


async def _search_rooms(
    db: AsyncSession,
    customer_id: uuid.UUID,
    query: str,
    room_type: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
    guests: int | None = None,
) -> dict:
    """Search for rooms in the database."""
    q = select(Room).where(Room.customer_id == customer_id, Room.available == True)

    if room_type:
        q = q.where(Room.room_type.ilike(f"%{room_type}%"))
    if min_price is not None:
        q = q.where(Room.price_per_night >= min_price)
    if max_price is not None:
        q = q.where(Room.price_per_night <= max_price)
    if guests:
        q = q.where(Room.capacity >= guests)

    # Also try text search on name/description
    if query:
        q = q.where(
            (Room.name.ilike(f"%{query}%")) |
            (Room.description.ilike(f"%{query}%")) |
            (Room.room_type.ilike(f"%{query}%"))
        )

    q = q.order_by(Room.price_per_night.asc()).limit(6)
    result = await db.execute(q)
    rooms = result.scalars().all()

    if not rooms:
        # Fallback: return all available rooms if search was too restrictive
        fallback = await db.execute(
            select(Room).where(Room.customer_id == customer_id, Room.available == True)
            .order_by(Room.price_per_night.asc()).limit(6)
        )
        rooms = fallback.scalars().all()

    if not rooms:
        return {"rooms": [], "message": "No rooms available at the moment."}

    return {
        "rooms": [_room_to_dict(r) for r in rooms],
        "message": f"Found {len(rooms)} room{'s' if len(rooms) != 1 else ''} available.",
    }


async def _make_booking_inquiry(
    db: AsyncSession,
    customer_id: uuid.UUID,
    room_id: str,
    guest_name: str,
    guest_email: str,
    check_in: str,
    check_out: str,
    guest_count: int,
    special_requests: str = "",
) -> dict:
    """Create a booking inquiry as a lead."""
    # Validate room exists
    result = await db.execute(
        select(Room).where(Room.id == uuid.UUID(room_id), Room.customer_id == customer_id)
    )
    room = result.scalar_one_or_none()
    if not room:
        return {"error": "Room not found"}

    # Create lead in UserProfile
    custom_fields = json.dumps({
        "type": "booking_inquiry",
        "room_name": room.name,
        "room_type": room.room_type,
        "check_in": check_in,
        "check_out": check_out,
        "guest_count": guest_count,
        "special_requests": special_requests,
        "price_per_night": room.price_per_night,
        "currency": room.currency,
    })

    profile = UserProfile(
        customer_id=customer_id,
        email=guest_email,
        name=guest_name,
        lead_intent="booking_inquiry",
        custom_fields=custom_fields,
    )
    db.add(profile)
    await db.commit()

    return {
        "message": f"Booking inquiry submitted for {room.name}! Check-in: {check_in}, Check-out: {check_out}, Guests: {guest_count}. The hotel will contact you at {guest_email} to confirm.",
        "booking": {
            "room_name": room.name,
            "check_in": check_in,
            "check_out": check_out,
            "guest_count": guest_count,
            "guest_email": guest_email,
        },
    }


def _room_to_dict(r: Room) -> dict:
    """Convert Room model to API-friendly dict."""
    return {
        "id": str(r.id),
        "name": r.name,
        "description": (r.description or "")[:300],
        "price": r.price_per_night,
        "currency": r.currency or "",
        "original_price": r.original_price,
        "images": json.loads(r.images) if r.images else [],
        "amenities": json.loads(r.amenities) if r.amenities else [],
        "capacity": r.capacity,
        "room_type": r.room_type or "",
        "available": r.available,
    }
