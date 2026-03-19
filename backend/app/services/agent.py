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

MAX_TOOL_ITERATIONS = 5

ECOMMERCE_SYSTEM_PROMPT = """You are a friendly and knowledgeable shopping assistant for {brand_name}.

YOUR ROLE:
- Help customers discover and buy products from {brand_name}'s catalog
- Use the product_search tool to find products matching what the customer is looking for
- Help with sizing advice, color recommendations, and product comparisons
- Manage the shopping cart (add items, remove items, show cart)
- Manage the wishlist (save items for later, view wishlist)
- Guide customers to checkout when ready
- Help customers check order status

TOOL USAGE:
- When a customer asks about products, ALWAYS use product_search to find real products
- When they want to add something, use add_to_cart
- When they ask about their cart, use get_cart
- When they want to checkout or buy, use checkout
- When they want to save for later or add to wishlist, use add_to_wishlist
- When they ask about their wishlist or saved items, use get_wishlist
- When they ask about an order, use get_order_status
- NEVER make up product names, prices, or details — only use data from tool results

CONVERSATION STYLE:
- Be warm, helpful, and concise
- Use product details from search results in your responses
- If no products match, suggest broadening the search
- Proactively suggest related items or complete outfits
- Always mention prices when discussing products

FORMATTING:
- Keep responses natural and conversational
- When showing products, mention name, price, and key details
- Don't use excessive markdown — keep it readable in chat
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
        # Build system prompt
        system_prompt = ECOMMERCE_SYSTEM_PROMPT.format(brand_name=brand_name)

        # Get conversation history
        history = self.conversation_store.get_messages(session_id)

        # Add user message
        self.conversation_store.add_message(session_id, "user", question)

        # Build messages for OpenAI
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": question})

        full_answer = ""
        iteration = 0

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            # Call OpenAI with tools
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=ECOMMERCE_TOOLS,
                max_tokens=800,
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
        suggestions = _generate_shopping_suggestions(full_answer)

        yield {
            "type": "done",
            "answer": full_answer,
            "suggestions": suggestions,
            "sources": [],
        }


def _generate_shopping_suggestions(answer: str) -> list[str]:
    """Generate contextual shopping suggestions based on the answer."""
    # Simple heuristic-based suggestions
    suggestions = []
    lower = answer.lower()

    if "cart" in lower or "added" in lower:
        suggestions.append("Show my cart")
        suggestions.append("Checkout")
    elif "wishlist" in lower or "saved" in lower:
        suggestions.append("Show my wishlist")
        suggestions.append("Show my cart")
    elif "order" in lower or "shipped" in lower:
        suggestions.append("Show my cart")
        suggestions.append("What's popular?")
    elif "product" in lower or "found" in lower:
        suggestions.append("Add to cart")
        suggestions.append("Show me more options")
    else:
        suggestions.append("What's popular?")
        suggestions.append("Show my cart")

    return suggestions[:2]


# Singleton
_agent_service: AgentService | None = None


def get_agent_service() -> AgentService:
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service
