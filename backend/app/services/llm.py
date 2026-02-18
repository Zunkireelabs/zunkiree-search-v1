from abc import ABC, abstractmethod
from openai import AsyncOpenAI
from app.config import get_settings
from app.utils.chunking import count_tokens

settings = get_settings()


# =============================================================================
# SYSTEM PROMPT TEMPLATE
# =============================================================================

SYSTEM_PROMPT_TEMPLATE = """You are a helpful assistant for {brand_name}.

INSTRUCTIONS:
- Answer questions ONLY using the provided context below
- If the answer is not in the context, say "{fallback_message}"
- Never make up information or provide information not in the context
- Keep responses concise, clear, and helpful
- Tone: {tone}
- Do not mention that you are using "context" or "provided information"
- Respond naturally as if you know this information directly

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
            return {
                "answer": fallback_message,
                "suggestions": [],
            }

        # Build system prompt
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            brand_name=brand_name,
            tone=tone,
            fallback_message=fallback_message,
            context=context,
        )

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
