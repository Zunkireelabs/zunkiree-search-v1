"""
Agentic AI service for the HR Goel demo (website_type == "it_solutions").
Public-receptionist agent: answers questions grounded in the ingested KB,
and slot-fills a quotation request (product, email, phone) before calling
the edgeX lead-submit tool. Modeled on hospitality_agent.py, with RAG
retrieval added for KB grounding (see HR-GOEL-AGENT-BRIEF.md, brain folder).

Same brain serves chat now; voice (Orca) is a follow-on — keep replies short.
"""
import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.services.conversation import get_conversation_store
from app.services.hr_goel_tools import HR_GOEL_TOOLS, execute_hr_goel_tool
from app.services.query import get_query_service
from app.config import get_settings
from app.services.openai_client import get_openai_client

logger = logging.getLogger("zunkiree.hr_goel_agent")
settings = get_settings()

MAX_TOOL_ITERATIONS = 3
MAX_CONTEXT_CHUNKS = 5

HR_GOEL_SYSTEM_PROMPT = """You are {brand_name}'s assistant. Be warm, professional, and concise — 1-2 short sentences per reply, plain text only (no markdown/bold/lists/links). Your replies are also read aloud on a voice channel, so keep them short and natural to say.

GROUNDING — this is the most important rule:
- Answer ONLY using the KNOWLEDGE BASE below. Never invent products, prices, specifications, or contact details that aren't in it.
- If the knowledge base doesn't cover the question, say you don't have that detail and offer to take a quotation request or have the team follow up. Do not guess.

QUOTATION FLOW: If the visitor wants a price/quote, follow these steps in order:
1. Ask WHICH product or service they want quoted (you can suggest a few from the knowledge base if it helps).
2. Once you know the product, ask for their EMAIL and PHONE NUMBER (both required).
3. Once you have product + email + phone, read them back for confirmation before calling submit_quote.
4. Only call submit_quote once all three are confirmed. Call it once per request.
5. After it succeeds, tell them their request is in and a confirmation email is on its way. Do not promise a price or timeline yourself — that's for the follow-up.

KNOWLEDGE BASE:
{context}
"""


def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "(no matching knowledge base content for this question)"
    parts = []
    for c in chunks[:MAX_CONTEXT_CHUNKS]:
        title = c.get("source_title") or "Source"
        parts.append(f"[{title}]\n{c['content']}")
    return "\n\n".join(parts)


class HrGoelAgentService:
    def __init__(self):
        self.client = get_openai_client("chat_retry")
        self.model = settings.llm_model
        self.conversation_store = get_conversation_store()
        self.query_service = get_query_service()

    async def process_agent_stream(
        self,
        db: AsyncSession,
        site_id: str,
        session_id: str,
        question: str,
        customer_id: uuid.UUID,
        customer: Customer,
        config: WidgetConfig | None,
        brand_name: str,
        channel: str = "chat",
    ):
        """
        Yields SSE events:
        - {"type": "token", "data": "..."}
        - {"type": "tool_call", "name": "...", "status": "running"|"done"}
        - {"type": "done", "answer": "...", "suggestions": [...], "sources": [...]}
        """
        retrieval = await self.query_service._retrieve_and_rank(
            db=db, customer=customer, config=config, site_id=site_id, question=question,
        )
        chunks = retrieval.get("chunks_for_llm") or []
        context = _format_context(chunks)

        system_prompt = HR_GOEL_SYSTEM_PROMPT.format(brand_name=brand_name, context=context)

        history = self.conversation_store.get_messages(session_id)
        self.conversation_store.add_message(session_id, "user", question)

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": question})

        full_answer = ""
        iteration = 0

        while iteration < MAX_TOOL_ITERATIONS:
            iteration += 1

            # Release the pooler connection before each LLM round-trip (see C1 notes).
            await db.commit()

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=HR_GOEL_TOOLS,
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
                    except ValueError:
                        tool_args = {}

                    yield {"type": "tool_call", "name": tool_name, "status": "running"}

                    result = await execute_hr_goel_tool(
                        tool_name=tool_name, tool_args=tool_args, session_id=session_id,
                    )

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

        yield {
            "type": "done",
            "answer": full_answer,
            "suggestions": [],
            "sources": [],
        }


_hr_goel_agent_service: HrGoelAgentService | None = None


def get_hr_goel_agent_service() -> HrGoelAgentService:
    global _hr_goel_agent_service
    if _hr_goel_agent_service is None:
        _hr_goel_agent_service = HrGoelAgentService()
    return _hr_goel_agent_service
