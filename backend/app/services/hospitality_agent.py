"""
Agentic AI service with tool-calling for hospitality (hotel) assistant.
Handles room browsing, availability inquiries, and booking lead capture.
"""
import json
import logging
import uuid
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.conversation import get_conversation_store
from app.services.hospitality_tools import HOSPITALITY_TOOLS, execute_hospitality_tool
from app.config import get_settings

logger = logging.getLogger("zunkiree.hospitality_agent")
settings = get_settings()

MAX_TOOL_ITERATIONS = 3

HOSPITALITY_SYSTEM_PROMPT = """You are {brand_name}'s hotel concierge assistant. Be warm, professional, and helpful. Keep responses to 1-2 sentences, plain text only (no markdown/bold/lists/links).

ROOMS: When showing rooms, the UI displays room cards automatically — NEVER list room details, prices, or images in text. Just say something like "Here are our available rooms!" or "Take a look at these options!"

BOOKING: To make a booking inquiry, you need: guest name, email, check-in date, check-out date, and number of guests. Ask for these details conversationally before calling make_booking_inquiry.

TOOLS: search_rooms, make_booking_inquiry.

You can also answer questions about the hotel's amenities, policies, location, dining, and nearby attractions from your knowledge.
"""


class HospitalityAgentService:
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
    ):
        """
        Process a query through the hospitality agentic pipeline.
        Yields SSE events:
        - {"type": "token", "data": "..."} for text tokens
        - {"type": "tool_call", "name": "...", "status": "running"|"done"}
        - {"type": "rooms", "data": [...]} for room results
        - {"type": "done", "answer": "...", "suggestions": [...]}
        """
        system_prompt = HOSPITALITY_SYSTEM_PROMPT.format(brand_name=brand_name)

        history = self.conversation_store.get_messages(session_id)
        self.conversation_store.add_message(session_id, "user", question)

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": question})

        full_answer = ""
        iteration = 0

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=HOSPITALITY_TOOLS,
                max_tokens=200,
                temperature=0.3,
                stream=True,
            )

            current_text = ""
            tool_calls_data: dict[int, dict] = {}

            async for chunk in response:
                delta = chunk.choices[0].delta

                if delta.content:
                    current_text += delta.content
                    yield {"type": "token", "data": delta.content}

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {"id": tc.id or "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_calls_data[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_data[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_data[idx]["arguments"] += tc.function.arguments

            if current_text and not tool_calls_data:
                full_answer = current_text
                break

            if tool_calls_data:
                tool_calls_list = []
                for idx in sorted(tool_calls_data.keys()):
                    tc = tool_calls_data[idx]
                    tool_calls_list.append({
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    })

                messages.append({
                    "role": "assistant",
                    "content": current_text or None,
                    "tool_calls": tool_calls_list,
                })

                for tc in tool_calls_list:
                    tool_name = tc["function"]["name"]
                    try:
                        tool_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        tool_args = {}

                    yield {"type": "tool_call", "name": tool_name, "status": "running"}

                    result = await execute_hospitality_tool(
                        tool_name=tool_name,
                        tool_args=tool_args,
                        db=db,
                        session_id=session_id,
                        customer_id=customer_id,
                        site_id=site_id,
                    )

                    if tool_name == "search_rooms" and "rooms" in result:
                        yield {"type": "rooms", "data": result["rooms"]}

                    yield {"type": "tool_call", "name": tool_name, "status": "done"}

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    })

                continue

            break

        if full_answer:
            self.conversation_store.add_message(session_id, "assistant", full_answer)

        suggestions = _generate_hospitality_suggestions(full_answer)

        yield {
            "type": "done",
            "answer": full_answer,
            "suggestions": suggestions,
            "sources": [],
        }


def _generate_hospitality_suggestions(answer: str) -> list[str]:
    """Generate contextual hospitality suggestions."""
    lower = answer.lower()

    if "booking" in lower or "inquiry" in lower or "confirm" in lower:
        return ["Check room availability", "Hotel amenities"]
    elif "room" in lower or "available" in lower:
        return ["Book a room", "What amenities do you have?"]
    elif "amenit" in lower or "facility" in lower:
        return ["Show me rooms", "How do I get there?"]
    else:
        return ["Show available rooms", "Hotel amenities"]


_hospitality_agent_service: HospitalityAgentService | None = None


def get_hospitality_agent_service() -> HospitalityAgentService:
    global _hospitality_agent_service
    if _hospitality_agent_service is None:
        _hospitality_agent_service = HospitalityAgentService()
    return _hospitality_agent_service
