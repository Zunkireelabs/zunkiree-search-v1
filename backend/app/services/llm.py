import logging
from abc import ABC, abstractmethod
from openai import AsyncOpenAI
from app.config import get_settings
from app.utils.chunking import count_tokens

logger = logging.getLogger("zunkiree.llm.service")

settings = get_settings()


# =============================================================================
# SYSTEM PROMPT TEMPLATE
# =============================================================================

SYSTEM_PROMPT_TEMPLATE = """You are a knowledgeable assistant for {brand_name}.

YOUR #1 RULE: Answer helpfully if the question relates to what {brand_name} does. Never refuse a relevant question.

ANSWERING:
- If the context below contains relevant information, use it as the basis for your answer.
- If context is sparse but the question is about {brand_name}'s general domain (services, processes, eligibility, etc.), give a helpful general answer.
- If context is sparse AND the question asks for something specific to {brand_name} (URLs, portal links, team names), say you don't have that specific detail and suggest the user contact {brand_name} directly.
{contact_info_block}

NEVER FABRICATE:
- NEVER invent URLs, email addresses, phone numbers, portal links, or contact details.
- NEVER make up specific prices, dates, deadlines, or policy details that are not in the context.
- If context doesn't contain a specific fact, do NOT guess it. Either omit it or say to check with {brand_name}.

WHEN TO USE THE FALLBACK:
- Respond with "{fallback_message}" ONLY if the question is completely off-topic (e.g., "what's the weather?") and has nothing to do with {brand_name}'s domain.

STYLE:
- Tone: {tone}
- Keep responses concise, clear, and actionable
- Respond naturally — never mention "context", "provided information", or "based on my data"

CONTEXT:
{context}
"""


# =============================================================================
# ABSTRACT BASE CLASS - LLM Provider Interface
# =============================================================================

class BaseLLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    Implement this interface to add support for new LLM providers.
    """

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> str:
        """
        Generate a response from the LLM.

        Args:
            system_prompt: System instructions for the LLM
            user_message: User's input message
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)

        Returns:
            Generated text response
        """
        pass


# =============================================================================
# OPENAI PROVIDER IMPLEMENTATION
# =============================================================================

class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider implementation."""

    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    async def generate(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 500,
        temperature: float = 0.3,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()


# =============================================================================
# LLM SERVICE - Business Logic Layer
# =============================================================================

class LLMService:
    """
    High-level LLM service for answer generation.
    Uses composition with BaseLLMProvider for flexibility.
    """

    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    async def generate_answer(
        self,
        question: str,
        context_chunks: list[dict],
        brand_name: str,
        tone: str = "neutral",
        fallback_message: str = "I don't have that information yet.",
        max_tokens: int = 500,
        show_suggestions: bool = True,
        user_email: str | None = None,
        user_profile: dict | None = None,
        contact_info: str | None = None,
    ) -> dict:
        """
        Generate an answer using the LLM.

        Args:
            question: User's question
            context_chunks: List of relevant chunks with 'content' key
            brand_name: Customer's brand name
            tone: Response tone (formal, neutral, friendly)
            fallback_message: Message to use when answer not found
            max_tokens: Maximum tokens in response
            show_suggestions: Whether to generate follow-up suggestions

        Returns:
            Dict with 'answer' and 'suggestions'
        """
        # Build context from chunks with source labels and token cap
        max_context_tokens = 4000
        context_parts = []
        running_tokens = 0

        for chunk in context_chunks:
            content = chunk.get("content", "")
            if not content:
                continue

            source_title = chunk.get("source_title", "")
            part = f"[Source: {source_title}]\n{content}" if source_title else content
            part_tokens = count_tokens(part)

            if running_tokens + part_tokens > max_context_tokens:
                break
            context_parts.append(part)
            running_tokens += part_tokens

        context = "\n\n---\n\n".join(context_parts)

        if not context.strip():
            context = f"No indexed documents matched this query. Use your general knowledge to answer. You are an expert assistant for {brand_name} — give a genuinely helpful, specific answer about their domain."

        # Build contact info block for the prompt
        if contact_info:
            contact_info_block = (
                f"PRICING & CONTACT: For questions about pricing, quotes, fees, costs, or anything requiring direct assistance, "
                f"direct the user to contact {brand_name} at {contact_info}. "
                f"You may use this contact info in your responses — it is verified and accurate."
            )
        else:
            contact_info_block = ""

        # Build system prompt
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            brand_name=brand_name,
            tone=tone,
            fallback_message=fallback_message,
            context=context,
            contact_info_block=contact_info_block,
        )

        if user_email:
            identity_parts = [f"The person asking is verified as {user_email}."]
            if user_profile:
                if user_profile.get("name"):
                    identity_parts.append(f"Their name is {user_profile['name']}.")
                if user_profile.get("user_type"):
                    identity_parts.append(f"Their user type is {user_profile['user_type'].replace('_', ' ')}.")
                if user_profile.get("lead_intent"):
                    identity_parts.append(f"Their lead intent is {user_profile['lead_intent'].replace('_', ' ')}.")
                custom = user_profile.get("custom_fields")
                if custom and isinstance(custom, dict):
                    for key, val in custom.items():
                        identity_parts.append(f"Their {key.replace('_', ' ')} is {val}.")
            identity_parts.append(
                "IMPORTANT: You know who this user is. "
                "Filter and personalize all answers using their profile data. "
                "Match context records to this user's email, name, or custom fields. "
                "If the question is about their status, eligibility, recommendations, or anything personal, "
                "search the context for records that relate to this specific user and present those results. "
                "Address them by name. Never tell them to 'check a portal' or 'log in elsewhere' — "
                "you ARE their portal. Answer directly with what the data shows about them."
            )
            system_prompt += "\nIDENTIFIED USER: " + " ".join(identity_parts) + "\n"

        # Generate answer using provider
        answer = await self.provider.generate(
            system_prompt=system_prompt,
            user_message=question,
            max_tokens=max_tokens,
            temperature=settings.llm_temperature,
        )

        # Generate follow-up suggestions only if enabled
        suggestions = []
        if show_suggestions:
            suggestions = await self._generate_suggestions(question, answer, brand_name)

        return {
            "answer": answer,
            "suggestions": suggestions,
            "context_tokens": running_tokens,
        }

    async def _generate_suggestions(
        self,
        question: str,
        answer: str,
        brand_name: str,
    ) -> list[str]:
        """Generate follow-up question suggestions."""
        try:
            system_prompt = (
                f"You are a helpful assistant for {brand_name}. "
                "Based on the conversation, suggest 2 brief follow-up questions "
                "the user might ask. Return only the questions, one per line, "
                "no numbering or bullets."
            )
            user_message = (
                f"User asked: {question}\n\n"
                f"Answer provided: {answer}\n\n"
                "Suggest 2 follow-up questions:"
            )

            suggestions_text = await self.provider.generate(
                system_prompt=system_prompt,
                user_message=user_message,
                max_tokens=100,
                temperature=0.7,
            )

            suggestions = [s.strip() for s in suggestions_text.split("\n") if s.strip()]
            return suggestions[:2]  # Limit to 2 suggestions
        except Exception:
            return []

    async def rerank_chunks(
        self,
        question: str,
        chunks: list[dict],
        top_n: int = 5,
    ) -> list[dict]:
        """
        Use LLM to rerank chunks by relevance to the question.
        Called only for ambiguous queries (0.25 < top_score < 0.45).

        Args:
            question: User's question
            chunks: List of chunk dicts with 'content' key
            top_n: Number of top chunks to return after reranking

        Returns:
            Reranked list of chunk dicts, trimmed to top_n
        """
        if len(chunks) <= 1:
            return chunks[:top_n]

        # Build numbered passage list (truncate each to ~400 chars for cost efficiency)
        passages = []
        for i, chunk in enumerate(chunks, 1):
            content = chunk.get("content", "")[:400]
            passages.append(f"Passage {i}: {content}")

        passages_text = "\n\n".join(passages)

        try:
            response = await self.provider.generate(
                system_prompt=(
                    "You are a relevance ranking assistant. "
                    "Given a question and numbered passages, return ONLY the passage numbers "
                    "ordered by relevance to the question, most relevant first. "
                    "Format: comma-separated numbers, e.g. 3,1,5,2,4"
                ),
                user_message=(
                    f"Question: {question}\n\n{passages_text}\n\n"
                    "Ranking (most relevant first):"
                ),
                max_tokens=50,
                temperature=0.0,
            )

            # Parse ranking response
            ranking = [int(x.strip()) for x in response.split(",") if x.strip().isdigit()]

            reranked = []
            seen = set()
            for idx in ranking:
                if 1 <= idx <= len(chunks) and idx not in seen:
                    reranked.append(chunks[idx - 1])
                    seen.add(idx)

            # Append any missing chunks at the end (fallback for incomplete rankings)
            for i, chunk in enumerate(chunks):
                if (i + 1) not in seen:
                    reranked.append(chunk)

            logger.info(
                "[RERANK] input_chunks=%d output_chunks=%d ranking=%s",
                len(chunks), min(top_n, len(reranked)), ranking[:top_n],
            )
            return reranked[:top_n]

        except Exception as e:
            logger.warning("[RERANK] Failed, returning original order: %s", e)
            return chunks[:top_n]


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

# Cache for service instances
_llm_services: dict[str, LLMService] = {}


def get_llm_service(model_tier: str = "default") -> LLMService:
    """
    Factory function to get LLM service instance.

    Args:
        model_tier: "default" for gpt-4o-mini, "premium" for gpt-4o

    Returns:
        LLMService instance configured with appropriate provider
    """
    global _llm_services

    if model_tier not in _llm_services:
        # Select model based on tier
        if model_tier == "premium":
            model = settings.llm_model_premium
        else:
            model = settings.llm_model

        # Create provider (currently only OpenAI supported)
        provider = OpenAIProvider(
            api_key=settings.openai_api_key,
            model=model,
        )

        # Create service with provider
        _llm_services[model_tier] = LLMService(provider)

    return _llm_services[model_tier]
