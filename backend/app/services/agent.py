"""
Agentic AI service with tool-calling for ecommerce shopping assistant.
Handles multi-turn conversations, product search, cart management, and checkout.
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

ECOMMERCE_SYSTEM_PROMPT = """You are a personal shopping advisor for {brand_name} — warm, knowledgeable, and genuinely helpful.

YOUR ROLE:
- Help customers discover products they'll love from {brand_name}'s catalog
- Give expert advice on fit, fabric, styling, and sizing — like a skilled in-store advisor
- Use the product "details" field to describe products richly (fabric, construction, silhouette, fit)
- Manage the shopping cart and guide to checkout when ready

PRODUCT KNOWLEDGE:
When product_search returns results, each product has a "details" field with rich information about fabric, construction, fit, and features. Use this to give genuinely helpful advice:
- Describe products with specifics: "The herringbone coat features a detachable shoulder panel and water-repellent cotton-nylon" — not just "a nice coat"
- When asked about sizing, use the available sizes and any fit details (oversized, tailored, relaxed) to recommend. If the customer shares their height or usual size, factor that into your recommendation
- Compare products by their distinct characteristics, not just price
- Suggest what occasions or weather each product suits

TOOL USAGE:
- When a customer asks about products, ALWAYS use product_search to find real products
- When they want to add something, use add_to_cart
- When they ask about their cart, use get_cart
- When they want to checkout or buy, use checkout
- NEVER make up product names, prices, or details — only use data from tool results

CONVERSATION STYLE:
- Be conversational and personal, not robotic
- Ask clarifying questions: "What's drawing you — something more tailored, or a relaxed drape?"
- After showing products, ask a follow-up to narrow preferences
- When a customer just says a size (e.g., "M" or "UK6"), treat it as an add-to-cart for the last discussed product
- Proactively suggest how to style or pair items

FORMATTING:
- Keep responses conversational — no bullet-point lists of products
- Weave product details naturally into your descriptions
- Don't use excessive markdown — keep it readable in a chat bubble
- Keep individual responses concise (2-4 sentences + follow-up question)
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
                    elif tool_name == "checkout" and "checkout" in result:
                        yield {"type": "checkout", "data": result["checkout"]}

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
