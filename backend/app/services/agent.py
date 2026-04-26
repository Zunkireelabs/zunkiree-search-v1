"""
Agentic AI service with tool-calling for ecommerce shopping assistant.
Handles multi-turn conversations, product search, cart management, wishlist, and checkout.
"""
import json
import logging
import uuid
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.conversation import get_conversation_store
from app.services.tools import ECOMMERCE_TOOLS, execute_tool
from app.config import get_settings

logger = logging.getLogger("zunkiree.agent")
settings = get_settings()

MAX_TOOL_ITERATIONS = 3

ECOMMERCE_SYSTEM_PROMPT = """You are {brand_name}'s shopping assistant. Talk like a friend, 1-2 sentences max, plain text only (no markdown/bold/lists/links).

PRODUCTS: UI shows product cards automatically — NEVER list products, prices, or image links. Just say a short comment like "Here are some options!" or "Found a few matches!"
- If "note" mentions "similar products": "We don't have that exact item, but check out these similar options!"
- If "note" says "no exact matches": "We don't carry that specific product, but here are the closest things we have!"
- If empty results: "We don't carry that right now" + suggest what's popular.

SIZING: Always confirm size before adding to cart. Ask "What size?" if not specified. The user can tap a size button below.

CHECKOUT: When user is ready to pay, ask "How would you like to pay — COD, Khalti, or eSewa?" The user can tap a payment button below.

TOOLS: product_search, add_to_cart, get_cart, remove_from_cart, checkout, add_to_wishlist, get_wishlist, get_order_status.
"""


class AgentService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.llm_model
        self.conversation_store = get_conversation_store()

    async def process_agent_stream(
        self,
        db: AsyncSession,
        site_id: str,
        session_id: str,
        question: str,
        customer_id: uuid.UUID,
        brand_name: str,
        image_data: str | None = None,
        system_prompt_override: str | None = None,
        conversation_history: list[dict] | None = None,
    ):
        """
        Process a query through the agentic pipeline with tool calling.
        Yields SSE events:
        - {"type": "token", "data": "..."} for text tokens
        - {"type": "tool_call", "name": "...", "status": "running"}
        - {"type": "products", "data": [...]} for product results
        - {"type": "cart_update", "data": {...}} for cart changes
        - {"type": "checkout", "data": {...}} for checkout data
        - {"type": "wishlist_update", "data": [...]} for wishlist changes
        - {"type": "address_form", "data": {...}} for inline address form
        - {"type": "done", "answer": "...", "suggestions": [...]}
        """
        # If image_data is provided, use GPT-4o Vision to describe the item
        if image_data:
            try:
                vision_response = await self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Describe this clothing item for a product search. Include: type of garment, color, material/texture, style. One sentence only."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                        ],
                    }],
                    max_tokens=100,
                )
                image_description = vision_response.choices[0].message.content
                question = f"Find products matching: {image_description}"
                logger.info("[AGENT] Vision description: %s", image_description)
            except Exception as e:
                logger.error("[AGENT] Vision API error: %s", e)
                question = "Show me your most popular products"

        # Build system prompt
        if system_prompt_override:
            system_prompt = system_prompt_override.format(brand_name=brand_name)
        else:
            system_prompt = ECOMMERCE_SYSTEM_PROMPT.format(brand_name=brand_name)

        # Load cart from DB if this is a returning session
        from app.services.cart import get_cart_service
        await get_cart_service().load_from_db(db, session_id)

        # Get conversation history — prefer DB-backed history when provided (e.g., from DM flow)
        if conversation_history is not None:
            history = conversation_history
        else:
            history = self.conversation_store.get_messages(session_id)

        # Add user message to in-memory store (for widget sessions)
        self.conversation_store.add_message(session_id, "user", question)

        # Build messages for OpenAI — keep last 10 messages to reduce latency
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": question})

        full_answer = ""
        iteration = 0
        last_tool_name = None
        last_tool_result = None

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            # Call OpenAI with tools
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=ECOMMERCE_TOOLS,
                max_tokens=200,
                temperature=0.3,
                stream=True,
            )

            # Stream the response
            current_text = ""
            tool_calls_data: dict[int, dict] = {}
            finish_reason = None

            async for chunk in response:
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason

                # Text content
                if delta.content:
                    current_text += delta.content
                    yield {"type": "token", "data": delta.content}

                # Tool calls (accumulated across chunks)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {
                                "id": tc.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_calls_data[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_data[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_data[idx]["arguments"] += tc.function.arguments

            # If we got text content and no tool calls, we're done
            if current_text and not tool_calls_data:
                full_answer = current_text
                break

            # Process tool calls
            if tool_calls_data:
                # Add assistant message with tool calls to conversation
                tool_calls_list = []
                for idx in sorted(tool_calls_data.keys()):
                    tc = tool_calls_data[idx]
                    tool_calls_list.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        },
                    })

                messages.append({
                    "role": "assistant",
                    "content": current_text or None,
                    "tool_calls": tool_calls_list,
                })

                # Execute each tool call
                for tc in tool_calls_list:
                    tool_name = tc["function"]["name"]
                    try:
                        tool_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}

                    # Signal tool execution
                    yield {"type": "tool_call", "name": tool_name, "status": "running"}

                    # Execute the tool
                    result = await execute_tool(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        db=db,
                        session_id=session_id,
                        customer_id=customer_id,
                        site_id=site_id,
                    )

                    last_tool_name = tool_name
                    last_tool_result = result

                    # Emit rich events based on tool type
                    if tool_name == "product_search" and "products" in result:
                        yield {"type": "products", "data": result["products"]}
                    elif tool_name in ("add_to_cart", "remove_from_cart", "get_cart") and "cart" in result:
                        yield {"type": "cart_update", "data": result["cart"]}
                    elif tool_name == "checkout":
                        if result.get("address_form_required"):
                            yield {"type": "address_form", "data": result["checkout"]}
                        elif "checkout" in result:
                            yield {"type": "checkout", "data": result["checkout"]}
                    elif tool_name in ("add_to_wishlist", "remove_from_wishlist", "get_wishlist") and "wishlist" in result:
                        yield {"type": "wishlist_update", "data": result["wishlist"]}

                    yield {"type": "tool_call", "name": tool_name, "status": "done"}

                    # Add tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    })

                # Continue the loop to get the assistant's response after tool results
                continue

            # No content and no tool calls — unusual, break
            break

        # Save assistant response to conversation
        if full_answer:
            self.conversation_store.add_message(session_id, "assistant", full_answer)

        # Generate suggestions
        suggestions = _generate_shopping_suggestions(full_answer, last_tool_name, last_tool_result)

        yield {
            "type": "done",
            "answer": full_answer,
            "suggestions": suggestions,
            "sources": [],
        }


def _generate_shopping_suggestions(
    answer: str,
    tool_name: str | None = None,
    tool_result: dict | None = None,
) -> list[str]:
    """Generate contextual shopping suggestions based on tool context and answer."""
    lower = answer.lower()

    # After product search — offer sizes if available
    if tool_name == "product_search" and tool_result:
        products = tool_result.get("products", [])
        if products:
            # Get sizes from the first product
            sizes = products[0].get("sizes", [])
            if sizes:
                return [f"Size {s}" for s in sizes[:4]]
            return ["Add to cart", "Show me more options"]
        return ["What's popular?", "Show me something else"]

    # After adding to cart
    if tool_name == "add_to_cart":
        if tool_result and "cart" in tool_result:
            return ["Checkout", "Continue shopping"]
        return ["Show my cart", "Continue shopping"]

    # After viewing cart
    if tool_name == "get_cart":
        return ["Checkout", "Continue shopping"]

    # During checkout flow
    if tool_name == "checkout":
        if tool_result and tool_result.get("address_form_required"):
            return []
        lower_answer = lower
        if "payment" in lower_answer or "pay" in lower_answer:
            return ["COD", "Khalti", "eSewa"]
        return ["COD", "Khalti", "eSewa"]

    # After wishlist actions
    if tool_name in ("add_to_wishlist", "get_wishlist"):
        return ["Show my cart", "Continue shopping"]

    # Fallback: heuristic on answer text
    if "cart" in lower or "added" in lower:
        return ["Checkout", "Continue shopping"]
    if "checkout" in lower or "payment" in lower or "how would you like to pay" in lower:
        return ["COD", "Khalti", "eSewa"]
    if "size" in lower or "what size" in lower:
        return ["Size S", "Size M", "Size L", "Size XL"]
    if "wishlist" in lower or "saved" in lower:
        return ["Show my wishlist", "Show my cart"]
    if "order" in lower or "confirmed" in lower or "placed" in lower:
        return ["Continue shopping", "What's popular?"]

    return ["What's popular?", "Show my cart"]


# Singleton
_agent_service: AgentService | None = None


def get_agent_service() -> AgentService:
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service
