"""
Chatbot query processor — wraps existing RAG pipeline with conversation context.
Produces DM-friendly answers grounded in the same knowledge base as the widget.
"""
import time
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, WidgetConfig
from app.models.chatbot import ChatbotChannel
from app.services.query import get_query_service
from app.services.llm import get_llm_service
from app.services.chatbot_conversation import get_chatbot_conversation_service

logger = logging.getLogger("zunkiree.chatbot.query")


REFINEMENT_SYSTEM_PROMPT = """You are {brand_name}'s assistant responding to a customer on {platform} DM. \
Your job is to answer helpfully using the knowledge base answer provided.

CONVERSATION SO FAR:
{history}

KNOWLEDGE BASE ANSWER:
{rag_answer}

Instructions:
- Use the knowledge base answer as your primary source of truth. Do not fabricate information.
- Adapt your response to the conversation context — don't repeat what you already said.
- Keep it concise and under 800 characters for DM readability.
- Do not use markdown formatting (no **, no ##, no bullet points with *). Use plain text.
- If the knowledge base answer suggests contacting the business, include the contact info.
- If the knowledge base answer is a fallback ("I don't have that information"), say so naturally.
- Be warm and helpful — this is a DM conversation, not a search result."""


class ChatbotQueryService:

    def __init__(self):
        self.query_service = get_query_service()
        self.llm_service = get_llm_service()
        self.conversation_service = get_chatbot_conversation_service()

    async def process_message(
        self,
        db: AsyncSession,
        channel: ChatbotChannel,
        sender_id: str,
        message_text: str,
    ) -> dict:
        """
        Process an incoming DM and return the answer.

        Returns: {"answer": str, "suggestions": list[str], "response_time_ms": int}
        """
        start = time.time()

        # Look up customer + site_id
        customer = await db.get(Customer, channel.customer_id)
        if not customer or not customer.is_active:
            return {
                "answer": "Sorry, this service is currently unavailable.",
                "suggestions": [],
                "response_time_ms": int((time.time() - start) * 1000),
            }

        # Get brand name from widget config
        config_result = await db.execute(
            select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
        )
        config = config_result.scalar_one_or_none()
        brand_name = config.brand_name if config else customer.name

        # Load conversation history
        history = await self.conversation_service.get_history(db, channel.id, sender_id)

        # Persist the user message
        await self.conversation_service.add_message(db, channel.id, sender_id, "user", message_text)

        # Call existing RAG pipeline (no origin validation for chatbot — it's server-to-server)
        try:
            rag_result = await self.query_service.process_query(
                db=db,
                site_id=customer.site_id,
                question=message_text,
                origin=None,  # Skip origin validation for chatbot
            )
        except Exception as e:
            logger.error("RAG pipeline error for channel %s: %s", channel.id, e)
            answer = f"Sorry, I'm having trouble finding an answer right now. Please try again later."
            await self.conversation_service.add_message(db, channel.id, sender_id, "assistant", answer)
            return {
                "answer": answer,
                "suggestions": [],
                "response_time_ms": int((time.time() - start) * 1000),
            }

        rag_answer = rag_result.get("answer", "")
        suggestions = rag_result.get("suggestions", [])

        # If conversation history exists, refine the answer with context
        if history:
            answer = await self._refine_with_history(
                rag_answer=rag_answer,
                history=history,
                question=message_text,
                brand_name=brand_name,
                platform=channel.platform,
            )
        else:
            # First message — strip markdown and return RAG answer directly
            answer = self._strip_markdown(rag_answer)

        # Ensure DM character limit
        if len(answer) > 950:
            answer = answer[:947] + "..."

        # Persist the assistant reply
        await self.conversation_service.add_message(db, channel.id, sender_id, "assistant", answer)

        return {
            "answer": answer,
            "suggestions": suggestions,
            "response_time_ms": int((time.time() - start) * 1000),
        }

    async def _refine_with_history(
        self,
        rag_answer: str,
        history: list[dict],
        question: str,
        brand_name: str,
        platform: str,
    ) -> str:
        """Use LLM to produce a conversational reply grounded in the RAG answer."""
        # Format conversation history
        formatted_history = "\n".join(
            f"{'Customer' if m['role'] == 'user' else 'You'}: {m['content']}"
            for m in history[-8:]  # Last 8 messages for prompt size control
        )

        system_prompt = REFINEMENT_SYSTEM_PROMPT.format(
            brand_name=brand_name,
            platform=platform.capitalize(),
            history=formatted_history,
            rag_answer=rag_answer,
        )

        try:
            answer = await self.llm_service.provider.generate(
                system_prompt=system_prompt,
                user_message=question,
                max_tokens=300,
                temperature=0.4,
            )
            return self._strip_markdown(answer)
        except Exception as e:
            logger.error("Refinement LLM error: %s", e)
            # Fall back to raw RAG answer
            return self._strip_markdown(rag_answer)

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove common markdown formatting for DM readability."""
        # Remove bold/italic markers
        text = text.replace("**", "").replace("__", "")
        text = text.replace("*", "").replace("_", "")
        # Remove headers
        lines = []
        for line in text.split("\n"):
            stripped = line.lstrip()
            if stripped.startswith("# "):
                lines.append(stripped.lstrip("# ").strip())
            elif stripped.startswith("- "):
                lines.append("  " + stripped[2:])
            else:
                lines.append(line)
        return "\n".join(lines).strip()


# Singleton
_chatbot_query_service: ChatbotQueryService | None = None


def get_chatbot_query_service() -> ChatbotQueryService:
    global _chatbot_query_service
    if _chatbot_query_service is None:
        _chatbot_query_service = ChatbotQueryService()
    return _chatbot_query_service
