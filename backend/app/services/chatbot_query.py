"""
Chatbot query processor — wraps existing RAG pipeline with conversation context.
Produces DM-friendly answers grounded in the same knowledge base as the widget.
"""
import json
import re
import time
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, WidgetConfig
from app.models.chatbot import ChatbotChannel
from app.services.query import get_query_service
from app.services.llm import get_llm_service, WEBSITE_TYPE_PROMPTS, LANGUAGE_NAMES
from app.services.chatbot_conversation import get_chatbot_conversation_service

logger = logging.getLogger("zunkiree.chatbot.query")


# ---------------------------------------------------------------------------
# Greeting detection (mirrors api/query.py but for DM context)
# ---------------------------------------------------------------------------

GREETING_WORDS = {
    "hi", "hello", "hey", "yo", "sup",
    "good morning", "good afternoon", "good evening",
    "hola", "namaste", "namaskar", "नमस्ते", "नमस्कार",
    # Romanized Nepali greetings
    "k cha", "ke cha", "kasto cha", "kasto", "hajur",
    "k ho", "ke ho", "kya cha",
}

GREETING_RESPONSES = {
    "ne": "नमस्ते! म {brand_name} हुँ। आज तपाईंलाई कसरी मद्दत गर्न सक्छु?",
    "hi": "नमस्ते! मैं {brand_name} हूँ। आज आपकी कैसे मदद कर सकता हूँ?",
}


# ---------------------------------------------------------------------------
# Common abbreviation dictionary for DM shorthand
# ---------------------------------------------------------------------------

COMMON_ABBREVIATIONS = {
    "pp": "price please",
    "pls": "please",
    "plz": "please",
    "abt": "about",
    "avail": "available",
    "qty": "quantity",
    "del": "delivery",
    "cod": "cash on delivery",
    "emi": "EMI installment",
    "tq": "thank you",
    "ty": "thank you",
    "thx": "thanks",
    "dm": "direct message",
    "asap": "as soon as possible",
    "rn": "right now",
    "tbh": "to be honest",
    "imo": "in my opinion",
    "w/o": "without",
    "b/w": "between",
    "govt": "government",
    "yr": "year",
    "yrs": "years",
    "min": "minimum",
    "max": "maximum",
    "approx": "approximately",
    "diff": "difference",
    "vs": "versus",
    "nos": "numbers",
    "pic": "picture",
    "pics": "pictures",
    "msg": "message",
    "info": "information",
    "ur": "your",
    "u": "you",
    "r": "are",
    "k": "okay",
    "ok": "okay",
    "thnx": "thanks",
    "phn": "phone",
    "amt": "amount",
    "promo": "promotion",
    "sz": "size",
    "clr": "color",
    "wht": "what",
    "hw": "how",
    "dis": "this",
    "dat": "that",
    "nw": "now",
}

# Feedback signal words (checked before RAG call)
POSITIVE_FEEDBACK_WORDS = {
    "thanks", "thank you", "thank u", "tq", "ty", "thx", "thnx",
    "helpful", "great", "perfect", "awesome", "got it", "understood",
    "nice", "cool", "good", "okay thanks", "ok thanks", "ok tq",
}
NEGATIVE_FEEDBACK_WORDS = {
    "wrong", "not helpful", "that's wrong", "thats wrong",
    "incorrect", "useless", "bad answer", "doesn't help",
    "not right", "galat",
}

# Tone directives
TONE_DIRECTIVES = {
    "formal": "Be professional and courteous. Use complete sentences. Address the customer respectfully.",
    "neutral": "Be helpful and clear. Balance professionalism with approachability.",
    "friendly": "Be warm and personable. Use casual, conversational language. Feel like a helpful friend.",
}


# ---------------------------------------------------------------------------
# DM-specific ecommerce agent system prompt
# ---------------------------------------------------------------------------

DM_ECOMMERCE_SYSTEM_PROMPT = """You are {brand_name}'s shopping assistant on Instagram DM. Talk like a friend, 1-2 sentences max, plain text only (no markdown/bold/lists/links).

PRODUCTS: When a customer asks about products, ALWAYS call product_search first.
Product images and cards are shown automatically as swipeable carousel cards in the DM.
- If products are found: say "Here's what I found!" or "Check these out!" — always be positive.
- If ZERO results: "We don't carry that right now" + suggest what's popular.
- NEVER say "we don't have" or "no exact match" when products ARE returned — the customer can see them.
- NEVER say "I can't show images" — images ARE shown as product cards.

SIZING: Show products first. Only ask about size when customer wants to add a specific product to cart.

CART: Customers can add to cart, view cart, and checkout all within this DM.

CHECKOUT: Collect info one at a time, then place the order. DO NOT re-ask anything already provided.
1. Name → 2. Phone → 3. Location (place name is enough) → 4. "COD or mobile banking?" → If mobile: "eSewa or Khalti?"
As SOON as you have all 4 (name, phone, location, payment_method), IMMEDIATELY call create_dm_order. Do NOT ask any more questions.
If payment_url is returned, share it and say "Tap this link to pay" followed by the URL.
Do NOT ask for email, postal code, or full address. Remember what the customer already told you.

TOOLS: product_search, add_to_cart, get_cart, remove_from_cart, checkout, create_dm_order, add_to_wishlist, get_wishlist, get_order_status.
"""

# ---------------------------------------------------------------------------
# System prompt template for DM refinement
# ---------------------------------------------------------------------------

REFINEMENT_SYSTEM_PROMPT = """You are {brand_name}'s representative responding to a customer on {platform} DM.
{website_type_instruction}

TONE: {tone_directive}

{history_section}

KNOWLEDGE BASE ANSWER:
{rag_answer}

{confidence_section}

Instructions:
- Use the knowledge base answer as your primary source of truth. Do not fabricate information.
- BE DIRECT. Give the exact answer — no filler, no padding, no unnecessary words.
- If the answer is a link, price, address, phone number, or any specific fact — just state it. Don't wrap it in extra sentences.
- A 1-line answer is perfectly fine. Don't stretch a short answer into a paragraph.
- Do NOT add introductions like "Sure!", "Of course!", "Great question!" or sign-offs like "Let me know if you need anything else."
- Do not use markdown formatting (no **, no ##, no bullet points with *). Use plain text only.
- Respond in a {tone_adjective} tone — {tone_brief}.
{contact_instruction}
{fallback_instruction}
{language_instruction}
- The customer may use informal language, abbreviations, or shorthand. Interpret their intent generously.
- Always respond in proper, complete language regardless of how the customer writes."""


class ChatbotQueryService:

    def __init__(self):
        self.query_service = get_query_service()
        self.llm_service = get_llm_service()
        self.conversation_service = get_chatbot_conversation_service()
        self._agent_service = None

    def _get_agent_service(self):
        if self._agent_service is None:
            from app.services.agent import get_agent_service
            self._agent_service = get_agent_service()
        return self._agent_service

    async def process_message(
        self,
        db: AsyncSession,
        channel: ChatbotChannel,
        sender_id: str,
        message_text: str,
    ) -> dict:
        """
        Process an incoming DM and return the answer.

        Returns: {"answer": str, "suggestions": list[str], "response_time_ms": int, "query_log_id": str | None}
        """
        start = time.time()

        # Look up customer + site_id
        customer = await db.get(Customer, channel.customer_id)
        if not customer or not customer.is_active:
            return {
                "answer": "Sorry, this service is currently unavailable.",
                "suggestions": [],
                "response_time_ms": int((time.time() - start) * 1000),
                "query_log_id": None,
            }

        # Get tenant config
        config_result = await db.execute(
            select(WidgetConfig).where(WidgetConfig.customer_id == customer.id)
        )
        config = config_result.scalar_one_or_none()

        brand_name = config.brand_name if config else customer.name
        tone = config.tone if config else "neutral"
        fallback_message = config.fallback_message if config else "I don't have that information yet. Please contact us directly for help."
        contact_email = config.contact_email if config else None
        contact_phone = config.contact_phone if config else None
        website_type = customer.website_type
        welcome_message = config.welcome_message if config else None
        supported_languages = _parse_json_list(config.supported_languages) if config and config.supported_languages else []

        # Parse quick_actions for greeting suggestions
        quick_actions = _parse_json_list(config.quick_actions) if config and config.quick_actions else []

        # Parse per-channel custom abbreviations from channel.config
        custom_abbreviations = {}
        if channel.config:
            try:
                ch_config = json.loads(channel.config) if isinstance(channel.config, str) else channel.config
                custom_abbreviations = ch_config.get("abbreviations", {})
            except Exception:
                pass

        # Load conversation history
        history = await self.conversation_service.get_history(db, channel.id, sender_id)

        # --- Check for feedback signals before doing anything else ---
        feedback_result = self._detect_feedback(message_text)
        if feedback_result and history:
            await self.conversation_service.add_message(db, channel.id, sender_id, "user", message_text)
            ack = "You're welcome! Let me know if you need anything else." if feedback_result == "positive" else "I'm sorry about that. Let me know how I can help better."
            await self.conversation_service.add_message(db, channel.id, sender_id, "assistant", ack)
            return {
                "answer": ack,
                "suggestions": [],
                "response_time_ms": int((time.time() - start) * 1000),
                "query_log_id": None,
                "feedback_signal": feedback_result,
            }

        # --- Check for greetings (skip RAG) ---
        cleaned = message_text.strip().lower()
        if cleaned in GREETING_WORDS:
            greeting = f"Hi there! I'm {brand_name}'s assistant. How can I help you today?"
            if welcome_message:
                greeting = f"Hi there! {welcome_message}"

            # Check if user's message is in Nepali/Hindi
            for lang_code, response_template in GREETING_RESPONSES.items():
                if cleaned in {"namaste", "namaskar", "नमस्ते", "नमस्कार"} and lang_code in supported_languages:
                    greeting = response_template.format(brand_name=brand_name)
                    break

            await self.conversation_service.add_message(db, channel.id, sender_id, "user", message_text)
            await self.conversation_service.add_message(db, channel.id, sender_id, "assistant", greeting)
            return {
                "answer": greeting,
                "suggestions": quick_actions[:3] if quick_actions else [],
                "response_time_ms": int((time.time() - start) * 1000),
                "query_log_id": None,
            }

        # Persist the user message
        await self.conversation_service.add_message(db, channel.id, sender_id, "user", message_text)

        # --- Expand abbreviations before sending to RAG ---
        expanded_text = self._expand_abbreviations(message_text, custom_abbreviations)

        # --- Route ecommerce tenants through the agent pipeline ---
        if website_type == "ecommerce":
            return await self._process_ecommerce_message(
                db=db,
                customer=customer,
                channel=channel,
                sender_id=sender_id,
                message_text=expanded_text,
                brand_name=brand_name,
                start=start,
            )

        # Call existing RAG pipeline
        try:
            rag_result = await self.query_service.process_query(
                db=db,
                site_id=customer.site_id,
                question=expanded_text,
                origin=None,  # Skip origin validation for chatbot
                user_agent=f"ZunkireeChatbot/{channel.platform}",
            )
        except Exception as e:
            logger.error("RAG pipeline error for channel %s: %s", channel.id, e)
            answer = "Sorry, I'm having trouble finding an answer right now. Please try again later."
            await self.conversation_service.add_message(db, channel.id, sender_id, "assistant", answer)
            return {
                "answer": answer,
                "suggestions": [],
                "response_time_ms": int((time.time() - start) * 1000),
                "query_log_id": None,
            }

        rag_answer = rag_result.get("answer", "")
        suggestions = rag_result.get("suggestions", [])
        meta = rag_result.get("_meta", {})
        top_score = meta.get("top_score")
        fallback_triggered = meta.get("fallback_triggered", False)
        query_log_id = meta.get("query_log_id")

        # --- Confidence-aware response ---
        if fallback_triggered:
            # Smart fallback: use tenant's custom message + contact info
            answer = self._build_smart_fallback(fallback_message, contact_email, contact_phone)
            suggestions = []  # No suggestions for fallback
        else:
            # Refine through conversational LLM for DM-friendly tone
            answer = await self._refine_with_history(
                rag_answer=rag_answer,
                history=history,
                question=message_text,
                brand_name=brand_name,
                platform=channel.platform,
                tone=tone,
                website_type=website_type,
                contact_email=contact_email,
                contact_phone=contact_phone,
                fallback_message=fallback_message,
                supported_languages=supported_languages,
                top_score=top_score,
            )

        # Ensure DM character limit
        if len(answer) > 950:
            answer = answer[:947] + "..."

        # Only show suggestions for product/service related queries
        if suggestions and not self._should_show_suggestions(expanded_text):
            suggestions = []

        # Persist the assistant reply
        await self.conversation_service.add_message(db, channel.id, sender_id, "assistant", answer)

        return {
            "answer": answer,
            "suggestions": suggestions,
            "response_time_ms": int((time.time() - start) * 1000),
            "query_log_id": query_log_id,
        }

    async def _process_ecommerce_message(
        self,
        db: AsyncSession,
        customer,
        channel: ChatbotChannel,
        sender_id: str,
        message_text: str,
        brand_name: str,
        start: float,
    ) -> dict:
        """Route ecommerce tenants through the agent pipeline (product search, cart, checkout)."""
        agent = self._get_agent_service()
        # Use sender_id as session_id for cart persistence across DM turns
        session_id = f"dm:{channel.id}:{sender_id}"

        answer = ""
        suggestions = []
        products = []

        try:
            async for event in agent.process_agent_stream(
                db=db,
                site_id=customer.site_id,
                session_id=session_id,
                question=message_text,
                customer_id=customer.id,
                brand_name=brand_name,
                system_prompt_override=DM_ECOMMERCE_SYSTEM_PROMPT,
            ):
                event_type = event.get("type")
                if event_type == "products":
                    products = event.get("data", [])
                elif event_type == "cart_update":
                    # Cart was modified — include cart info in answer
                    pass
                elif event_type == "done":
                    answer = event.get("answer", "")
                    suggestions = event.get("suggestions", [])
        except Exception as e:
            logger.error("Agent pipeline error for channel %s: %s", channel.id, e, exc_info=True)
            answer = "Sorry, I'm having trouble right now. Please try again."

        # Strip markdown for DM
        answer = self._strip_markdown(answer)
        if len(answer) > 950:
            answer = answer[:947] + "..."

        # Persist
        await self.conversation_service.add_message(db, channel.id, sender_id, "assistant", answer)

        return {
            "answer": answer,
            "suggestions": suggestions,
            "products": products,  # Product cards for carousel display
            "response_time_ms": int((time.time() - start) * 1000),
            "query_log_id": None,
        }

    async def _refine_with_history(
        self,
        rag_answer: str,
        history: list[dict],
        question: str,
        brand_name: str,
        platform: str,
        tone: str = "neutral",
        website_type: str | None = None,
        contact_email: str | None = None,
        contact_phone: str | None = None,
        fallback_message: str = "I don't have that information yet.",
        supported_languages: list[str] | None = None,
        top_score: float | None = None,
    ) -> str:
        """Use LLM to produce a conversational reply grounded in the RAG answer."""
        # History section
        if history:
            formatted_history = "\n".join(
                f"{'Customer' if m['role'] == 'user' else 'You'}: {m['content']}"
                for m in history[-8:]
            )
            history_section = f"CONVERSATION SO FAR:\n{formatted_history}\n\nAdapt your response to the conversation context — don't repeat what you already said."
        else:
            history_section = "This is the customer's first message. Greet them briefly and answer their question."

        # Website type instruction
        website_type_instruction = WEBSITE_TYPE_PROMPTS.get(website_type, "") if website_type else ""

        # Tone mapping
        tone_directive = TONE_DIRECTIVES.get(tone, TONE_DIRECTIVES["neutral"])
        tone_map = {"formal": ("professional", "like a courteous business representative"),
                     "neutral": ("helpful", "clear and approachable"),
                     "friendly": ("warm", "like a helpful friend chatting casually")}
        tone_adjective, tone_brief = tone_map.get(tone, tone_map["neutral"])

        # Contact instruction
        contact_parts = []
        if contact_email:
            contact_parts.append(f"email at {contact_email}")
        if contact_phone:
            contact_parts.append(f"call at {contact_phone}")
        contact_instruction = ""
        if contact_parts:
            contact_instruction = f"- If the customer needs help you can't provide, suggest they reach out via {' or '.join(contact_parts)}."

        # Fallback instruction
        fallback_instruction = f'- If you cannot answer from the knowledge base: "{fallback_message}"'

        # Language instruction — must be strict to avoid unwanted language switching
        language_instruction = "- ALWAYS respond in English by default. Only respond in another language if the customer's message is CLEARLY and ENTIRELY written in that language (e.g., full Nepali sentences in Devanagari or Romanized Nepali). Do NOT switch languages based on brand name, context clues, or mixed-language messages."
        if supported_languages and len(supported_languages) > 0:
            lang_names = [LANGUAGE_NAMES.get(code, code) for code in supported_languages if code != "en"]
            if lang_names:
                language_instruction = f"- ALWAYS respond in English by default. Only switch to {', '.join(lang_names)} if the customer's ENTIRE message is clearly written in that language. If the message is in English or a mix of English and another language, respond in English."

        # Confidence section
        confidence_section = ""
        if top_score is not None:
            if top_score < 0.4:
                confidence_section = "NOTE: The knowledge base has limited information on this topic. Be honest about what you know and suggest contacting the business directly for specifics."
            elif top_score < 0.6:
                confidence_section = "NOTE: The knowledge base has some relevant information but may not fully cover this topic. Answer based on what's available."

        system_prompt = REFINEMENT_SYSTEM_PROMPT.format(
            brand_name=brand_name,
            platform=platform.capitalize(),
            website_type_instruction=website_type_instruction,
            tone_directive=tone_directive,
            tone_adjective=tone_adjective,
            tone_brief=tone_brief,
            history_section=history_section,
            rag_answer=rag_answer,
            confidence_section=confidence_section,
            contact_instruction=contact_instruction,
            fallback_instruction=fallback_instruction,
            language_instruction=language_instruction,
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
            return self._strip_markdown(rag_answer)

    @staticmethod
    def _expand_abbreviations(text: str, custom_abbreviations: dict | None = None) -> str:
        """Expand common DM abbreviations to full words for better RAG retrieval."""
        # Merge common + custom
        abbrevs = dict(COMMON_ABBREVIATIONS)
        if custom_abbreviations:
            abbrevs.update(custom_abbreviations)

        words = text.split()
        expanded = []
        for word in words:
            clean = word.lower().rstrip(".,!?;:")
            trailing = word[len(clean):]  # Preserve trailing punctuation
            if clean in abbrevs:
                expanded.append(abbrevs[clean] + trailing)
            else:
                expanded.append(word)
        return " ".join(expanded)

    @staticmethod
    def _detect_feedback(message_text: str) -> str | None:
        """Detect if message is a feedback signal. Returns 'positive', 'negative', or None."""
        cleaned = message_text.strip().lower()
        if cleaned in POSITIVE_FEEDBACK_WORDS:
            return "positive"
        if cleaned in NEGATIVE_FEEDBACK_WORDS:
            return "negative"
        # Also check if it starts with a feedback phrase
        for phrase in POSITIVE_FEEDBACK_WORDS:
            if cleaned.startswith(phrase) and len(cleaned) < len(phrase) + 10:
                return "positive"
        for phrase in NEGATIVE_FEEDBACK_WORDS:
            if cleaned.startswith(phrase) and len(cleaned) < len(phrase) + 10:
                return "negative"
        return None

    @staticmethod
    def _should_show_suggestions(query: str) -> bool:
        """
        Show suggestions ONLY when user is clearly browsing/exploring.
        Default is False — suggestions are the exception, not the rule.
        """
        query_lower = query.lower().strip()

        # Only show for product/service exploration queries
        EXPLORE_SIGNALS = {
            "show", "tell me about", "what do you", "which", "any",
            "best", "recommend", "option", "alternative", "similar",
            "compare", "product", "service", "package", "plan", "offer",
            "menu", "list", "collection", "category",
        }
        for signal in EXPLORE_SIGNALS:
            if signal in query_lower:
                return True

        return False

    @staticmethod
    def _build_smart_fallback(
        fallback_message: str,
        contact_email: str | None,
        contact_phone: str | None,
    ) -> str:
        """Build a concise fallback response with contact info."""
        # Keep it short — no filler phrases
        contact_parts = []
        if contact_email:
            contact_parts.append(contact_email)
        if contact_phone:
            contact_parts.append(contact_phone)
        if contact_parts:
            return f"I don't have that info yet. Contact us: {' / '.join(contact_parts)}"
        return fallback_message

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove common markdown formatting for DM readability."""
        text = text.replace("**", "").replace("__", "")
        text = text.replace("*", "").replace("_", "")
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


def _parse_json_list(value: str | None) -> list:
    """Safely parse a JSON string that should be a list."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# Singleton
_chatbot_query_service: ChatbotQueryService | None = None


def get_chatbot_query_service() -> ChatbotQueryService:
    global _chatbot_query_service
    if _chatbot_query_service is None:
        _chatbot_query_service = ChatbotQueryService()
    return _chatbot_query_service
