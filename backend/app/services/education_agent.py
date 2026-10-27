"""
Education counselor agent (website_type == "education"): the generative-UI agent.

Per turn:
  1. Load the student's profile; apply a tapped block action deterministically.
  2. `detect_intent` (code, not LLM) maps core questions to a fixed tool -> block.
     The block is built from the tenant catalog + profile and emitted as a
     `ui_block` SSE event. The LLM then only writes a one-line lead-in.
  3. Anything else goes to the LLM with the UI tools available, grounded on the
     knowledge base (RAG), the same tool loop as hr_goel_agent.

The LLM never designs a block, and never states costs/requirements from memory.
Channel-agnostic: every block has `fallback_text`, so voice/IG/Orca adapters can
render text (shape per channel, no per-channel logic here).
"""
import json
import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.customer import Customer
from app.models.widget_config import WidgetConfig
from app.schemas.ui_blocks import UIBlock
from app.services.clinic_agent import _LANGUAGE_DIRECTIVES  # reuse the SAME strings dental-city ships
from app.services.education_catalog import Catalog, get_catalog
from app.services.education_compositions import chip_intent, compose, counselor_block, normalized_args
from app.services.education_actions import validate_block_action
from app.services.education_grounding import build_support, check_answer
from app.services.education_followup import RESULT_INTENTS, record_ui_state, resolve_country_switch, resolve_refinement
from app.services.education_kb_blocks import PENDING_LABELS, SHAPE_TO_BLOCK, classify_shape, kb_block, looks_like_question
from app.services.education_leadins import KB_FOUND, KB_MISS, NEEDS_DETAILS, leadin_for
from app.services.education_memory import DbEducationMemory
from app.services.education_scores import extract_scores
from app.services.education_sources import link_for_turn
from app.services.education_understanding import decide as decide_understanding, understand
from app.services.education_profile import (
    FIELD_LABELS, apply_block_action, apply_updates, display_value, missing_slots, progress, set_field,
)
from app.services.education_tools import EDUCATION_TOOLS, ToolOutcome, execute_education_tool, tool_for_intent
from app.services.education_ui_registry import TOOL_TO_INTENT, country_goal, detect_intent, journey_intent
from app.services.language_detection import detect_language
from app.services.openai_client import get_openai_client
from app.services.query import get_query_service

logger = logging.getLogger("zunkiree.education_agent")
settings = get_settings()

MAX_TOOL_ITERATIONS = 3
MAX_CONTEXT_CHUNKS = 5

EDUCATION_SYSTEM_PROMPT = """You are {brand_name}'s study-abroad assistant. Be warm, professional and concise: 1-2 short sentences per reply, plain text only (no markdown, bold, lists or links).

LANGUAGE: Reply in the same language the student's LATEST message is written in. Never switch languages yourself. A tool may return a message in English; convey its outcome in the student's language.

CARDS: Interactive cards (country picker, budget slider, matches, comparison, eligibility, profile, contact form) are shown by TOOLS; you cannot draw them. When the student asks something a card answers, call the tool instead of describing it in text. Never repeat numbers, countries or requirements a card already shows. If a tool says nothing was shown, follow its instruction (ask in plain text, or offer a counselor). Never write markers like [Card shown]; those are internal notes.

PROFILE: When the student states a fact about themselves (country, level, subject, budget, intake, English or academic score), call update_profile with it. Never ask again for something already known. Ask ONE question at a time.

GROUNDING (most important): Answer ONLY from the KNOWLEDGE BASE below and tool results. Do not use your general knowledge about visas, universities, costs, deadlines, requirements, steps or procedures, even if you are sure of them. If the knowledge base only says that something is offered (for example "visa guidance") but not how it works, do NOT explain how it generally works: say what the knowledge base says and that you don't have the detail, then offer a counselor (show_lead_form). Never invent or guess.

NO STALLING: You cannot look things up in the background. Never say you will check, look into or find something, or ask the student to wait or hold on. Answer now from what you have, or say you don't have it.

CONTACT DETAILS: Nothing is sent to the team yet, so NEVER promise that a counselor will call, email or contact them, or give any timeline. When you show the contact form just ask them to fill it in; after they submit, thank them and say their details are noted.

WHAT YOU KNOW ABOUT THE STUDENT:
{profile_block}

KNOWLEDGE BASE:
{context}
{language_directive}"""

# Which tool collects each missing profile slot.
_SLOT_ASKS = {
    "countries": "show_choice(kind=countries)",
    "study_level": "show_choice(kind=study_level)",
    "field_of_study": "ask in plain text",
    "budget": "show_budget_slider",
    "intake": "show_choice(kind=intake)",
    "english_score": "ask in plain text (test and score)",
}


def _format_context(chunks: list[dict]) -> str:
    if not chunks:
        return "(no matching knowledge base content for this question)"
    return "\n\n".join(f"[{c.get('source_title') or 'Source'}]\n{c['content']}" for c in chunks[:MAX_CONTEXT_CHUNKS])


def _profile_block(profile: dict, catalog: Catalog) -> str:
    known = []
    labels = catalog.labels()
    for field, label in FIELD_LABELS.items():
        value = profile.get(field)
        if not value:
            continue
        if field in ("countries", "focus_country"):
            value = [labels.get(v, v) for v in value] if isinstance(value, list) else labels.get(value, value)
        known.append(f"- {label}: {display_value(field, value, catalog.currency)}")
    contact = profile.get("contact") or {}
    if contact:
        known.append("- Contact details: provided")
    lines = known or ["- (nothing yet)"]
    missing = missing_slots(profile)
    if missing:
        lines.append("Not known yet (ask for the most useful ONE when it fits the conversation): "
                     + "; ".join(f"{FIELD_LABELS[f].lower()} via {_SLOT_ASKS[f]}" for f in missing))
    return "\n".join(lines)


# Taps that answer a block (the widget then shows it collapsed to a summary).
_ANSWER_ACTIONS = {"select", "set_value", "start", "submit"}

# The card that collects each profile slot. Slots not listed here are asked in plain text by the LLM.
_SLOT_CARD: dict[str, tuple[str, dict]] = {
    "countries": ("choice", {"kind": "countries"}),
    "study_level": ("choice", {"kind": "study_level"}),
    "budget": ("budget", {}),
    "intake": ("choice", {"kind": "intake"}),
}


def _ask_for_budget(profile: dict, catalog: Catalog) -> ToolOutcome | None:
    """Countries can't be ranked yet. Ask the one useful thing (the yearly budget) with the slider, instead of leaving the
    reply to the LLM. None when the budget is already known (asking again would loop) or the catalog has no costs to slide over."""
    if profile.get("budget"):
        return None
    ask = execute_education_tool("show_budget_slider", {}, profile, catalog)
    return ask if ask.block else None


_ACK = re.compile(r"^(ok(ay)?|yes|yeah|yep|sure|alright|continue|next|go ahead|let'?s go|proceed)[\s.!]*$", re.I)


def _next_card(profile: dict, catalog: Catalog) -> tuple[str, dict] | None:
    """The card for the first missing profile slot, or None when the next question is text-only / nothing is missing."""
    for slot in missing_slots(profile):
        if slot not in _SLOT_CARD:
            return None
        intent, args = _SLOT_CARD[slot]
        if intent == "choice" and slot == "countries" and not catalog.countries:
            continue
        return intent, args
    return None


def _turn_intent(question: str, block_action: dict | None, catalog: Catalog, profile: dict) -> tuple[str, dict] | None:
    """
    Deterministic routing, so the core flow never depends on the LLM following a prompt rule:
      - tapped welcome tile     -> that journey's first step
      - tapped 'explore'        -> that country's facts
      - tapped 'open_university' -> that university's facts and courses
      - picked a country for a pending goal (eligibility / costs) -> that goal, for that country
      - tapped answer (select / set_value) -> the next missing slot's card
      - typed text              -> detect_intent
    Anything else returns None and the knowledge-base shapes / the LLM take over.
    """
    if block_action:
        action_id = block_action.get("actionId")
        values = block_action.get("values") or {}
        if block_action.get("blockType") == "quick_chips":
            return chip_intent(str(action_id), catalog)   # a next-step button: a closed id -> intent, or nothing
        if action_id == "start":
            return journey_intent(values.get("journey", ""), profile, catalog)
        if action_id == "open_university":
            university = values.get("university_id")
            return ("university", {"university": university}) if catalog.get_university(str(university or "")) else None
        if action_id == "explore":
            country = values.get("country")
            return ("country_facts", {"country": country}) if catalog.get(country or "") else None
        if action_id == "select" and values.get("field") == "focus_country" and profile.get("goal"):
            goal = profile.pop("goal")
            return country_goal(goal, [profile["focus_country"]], profile, catalog) if profile.get("focus_country") else None
        if action_id in ("select", "set_value"):
            if profile.get("awaiting") == "recommend_country" and values.get("field") == "budget" and profile.get("budget"):
                profile.pop("awaiting")                  # the student asked "which country is best?" and this was the missing detail:
                return "recommend_country", {}           # finish that answer instead of moving on to the next checklist question
            return _next_card(profile, catalog)  # None = next question is text-only, so the LLM asks it
        return None
    if _ACK.match(question.strip()):
        return _next_card(profile, catalog)      # a bare "okay" keeps the guided flow moving
    return detect_intent(question, catalog, profile)


class EducationAgentService:
    def __init__(self):
        self.client = get_openai_client("chat_retry")
        self.model = settings.llm_model
        self.memory_for = DbEducationMemory  # db -> memory; tests swap in an in-memory one
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
        block_action: dict | None = None,
    ):
        """
        Yields SSE events:
        - {"type": "ui_block", "block": {...}}
        - {"type": "token", "data": "..."}
        - {"type": "tool_call", "name": "...", "status": "running"|"done"}
        - {"type": "done", "answer": "...", "suggestions": [], "sources": []}
        """
        catalog = get_catalog(site_id)
        memory = self.memory_for(db)
        profile = await memory.load_profile(customer_id, session_id)
        history, seen_titles = await memory.load_history(customer_id, session_id)

        if block_action and settings.education_validate_block_actions:
            origin = await memory.find_block(customer_id, session_id, str(block_action.get("blockId") or ""))
            if reason := validate_block_action(block_action, origin):
                logger.warning("[EDU] rejected block_action reason=%s block=%s action=%s",
                               reason, str(block_action.get("blockId"))[:40], str(block_action.get("actionId"))[:20])
                block_action = None  # degrade to the typed text; nothing from the tap is applied

        # What a typed message MEANS, read by one small constrained AI call (a flag; see education_understanding.py). The AI only picks
        # from fixed lists and the code validates it; below the confidence floor, on a failure or a timeout this is None or ignored and
        # the keyword rules decide exactly as before. A tap is already a closed id, so it never asks.
        followup = resolve_country_switch(question, profile, catalog) if block_action is None else None   # "what about Canada?": decided by the card on screen, no AI needed
        understanding, min_confidence = None, settings.education_understanding_min_confidence
        if block_action is None and followup is None and settings.education_ai_understanding:
            understanding = await understand(self.client, self.model, question, catalog=catalog, profile=profile)
        ai_choice = decide_understanding(understanding, min_confidence)

        changed = apply_block_action(profile, block_action)
        if block_action is None:
            profile.pop("awaiting", None)   # a typed message decides what is wanted now; a pending recommendation is set again below if it is still needed
            if understanding is not None and understanding.confidence >= min_confidence:
                changed += apply_updates(profile, understanding.score_updates())   # own, range-checked scores in any language; the rules below win a tie
            # Scores the student states in their own words are saved here, with their unit, before any card is chosen: the AI
            # sometimes asks "check eligibility" before it saves what was just said, and drops the word "gpa" when it does.
            changed += apply_updates(profile, extract_scores(question))
        # No cross-device merge on a submitted email: a typed email is not proof of identity, and merging let anyone who
        # typed a student's email see that student's profile. `find_profile_by_email` + `merge_profiles` stay for a merge
        # done after the email is verified.
        if changed:
            await memory.save_profile(customer_id, session_id, profile)  # a tap survives even if the stream is dropped
        if block_action and block_action.get("blockId") and block_action.get("actionId") in _ANSWER_ACTIONS:
            await memory.mark_answered(customer_id, session_id, block_action["blockId"], block_action.get("values") or {})

        shown: list[UIBlock] = []
        outcome: ToolOutcome | None = None
        templated: str | None = None   # the card's lead-in when code can write it (English only), else the LLM does
        can_template = settings.education_template_leadins and detect_language(question) == "en"
        # A short follow-up on the card on screen is resolved in code and re-runs the SAME intent, so the student gets
        # the same UI with new data: an explicit "what about Canada?" first (the keyword rules would read it as plain
        # facts), then a refinement such as "only under $30k" once the keyword rules have declined the message.
        if followup:
            intent = (followup.intent, followup.args)
        elif ai_choice and ai_choice[0] == "card":
            intent = ai_choice[1]             # a card the AI understood the student wants, for a country that exists in the catalog
        elif ai_choice:
            intent = None                     # a knowledge-base question (visa, process...): the keyword rules must not turn it into a card
        else:
            intent = _turn_intent(question, block_action, catalog, profile)
        if intent is None and block_action is None and not ai_choice:
            followup = resolve_refinement(question, profile, catalog)
            if followup:
                intent = (followup.intent, followup.args)
        source = "followup" if followup else "ai" if (ai_choice and ai_choice[0] == "card") else "rule"
        if followup:
            for field_name, value in followup.updates.items():
                set_field(profile, field_name, value)

        # A tapped journey tile can ask for a knowledge-base answer ("How to apply") instead of a catalog card.
        shape_request: dict | None = None
        if intent and intent[0] == "kb_shape":
            shape_request, intent = intent[1], None

        if intent:
            name, args = tool_for_intent(intent[0]), dict(intent[1])
            logger.info("[EDU] intent=%s source=%s tool=%s arg_keys=%s", intent[0], source, name, sorted(args))
            if goal := args.pop("goal", None):
                profile["goal"] = goal  # remembered so the next tap (which country?) continues the same goal
            if args.get("country"):
                set_field(profile, "focus_country", args["country"])
            yield {"type": "tool_call", "name": name, "status": "running"}
            outcome = execute_education_tool(name, args, profile, catalog)
            yield {"type": "tool_call", "name": name, "status": "done"}
            needs_details = False
            if outcome.block is None and intent[0] == "recommend_country" and settings.education_template_leadins:
                if ask := _ask_for_budget(profile, catalog):
                    needs_details = True
                    profile["awaiting"] = "recommend_country"   # the budget tap that answers the slider finishes this recommendation
                    outcome = ToolOutcome(ask.block, ask.message + " It appears because countries can't be ranked until you know "
                                          "their budget: say that in one short sentence and do not suggest any country.")
            if outcome.block and needs_details:
                shown.append(outcome.block)
                yield {"type": "ui_block", "block": outcome.block.model_dump()}
                if can_template:
                    templated = NEEDS_DETAILS
            elif outcome.block:
                record_ui_state(profile, intent[0], args)
                blocks = compose(intent[0], args, outcome.block, profile, catalog) if settings.education_compositions else [outcome.block]
                if len(blocks) > 1:
                    outcome = ToolOutcome(outcome.block, outcome.message + " Related blocks and next-step buttons appear with it; "
                                          "do not list, repeat or describe them.")
                for block in blocks:
                    shown.append(block)
                    yield {"type": "ui_block", "block": block.model_dump()}
                if can_template:
                    templated = leadin_for(intent[0], args, outcome.block, catalog, brand_name)

        # Knowledge-base lookup: for free-form questions and for "How to apply"; never for card turns or taps.
        context = "(not needed for this turn)"
        chunks: list[dict] = []   # knowledge-base text retrieved this turn; also what a free-text answer may rest on
        kb_miss = False
        kb_single_fact = False
        if intent is None and block_action is None and shape_request is None:
            logger.info("[EDU] no_rule_match chars=%d words=%d lang=%s question_like=%s", len(question), len(question.split()),
                        detect_language(question), looks_like_question(question))
        if intent is None and (block_action is None or shape_request):
            query_text = shape_request["query"] if shape_request else question
            shape = shape_request["shape"] if shape_request else await classify_shape(self.client, self.model, question)
            if shape:
                # Tell the widget what's coming so it can show a matching skeleton instead of a frozen screen.
                yield {"type": "ui_pending", "block_type": SHAPE_TO_BLOCK[shape], "label": PENDING_LABELS[shape]}

            retrieval = await self.query_service._retrieve_and_rank(
                db=db, customer=customer, config=config, site_id=site_id, question=query_text,
                skip_rerank=(channel == "voice"),
            )
            chunks = retrieval.get("chunks_for_llm") or []
            context = _format_context(chunks)

            # Open question -> interactive component built from that knowledge-base text, by the answer's shape.
            if shape:
                block = await kb_block(self.client, self.model, profile, shape, query_text, chunks)
                if block:
                    shown.append(block)
                    yield {"type": "ui_block", "block": block.model_dump()}
                    if can_template:
                        templated = KB_FOUND
                    outcome = ToolOutcome(block, (
                        f"The student now sees '{block.title}' right below your reply, built from the knowledge base. "
                        "Write ONE short, natural sentence introducing it (like 'Here's how it works:'). "
                        "Do not repeat its contents and do not say 'component', 'interactive' or 'guide'."))
                elif chunks and shape in ("timeline", "offerings"):
                    # No card could be built, but the knowledge base did return text: "how long does the UK visa take?" or "do you offer
                    # scholarships?" is often a single fact. Let the model answer from that text only; the grounding check still applies.
                    # Step-by-step and checklist questions stay a strict miss: the model must never write steps from general knowledge.
                    kb_single_fact = True
                else:
                    kb_miss = True
                    if settings.education_compositions:
                        counselor = counselor_block(catalog)
                        shown.append(counselor)
                        yield {"type": "ui_block", "block": counselor.model_dump()}
                        if can_template:
                            templated = KB_MISS   # the counselor button is on screen, so the sentence can point to it

        system_prompt = EDUCATION_SYSTEM_PROMPT.format(
            brand_name=brand_name,
            profile_block=_profile_block(profile, catalog),
            context=context,
            language_directive=_LANGUAGE_DIRECTIVES.get(detect_language(question), ""),
        )

        await memory.append_message(customer_id, session_id, "user", question)
        messages = [{"role": "system", "content": system_prompt}]
        if seen_titles:
            messages.append({"role": "system", "content": "Cards the student has already seen in this chat (oldest first): "
                             + "; ".join(seen_titles) + ". Don't re-ask what they answered; this is not text to repeat."})
        messages.extend(history[-10:])
        messages.append({"role": "user", "content": question})

        if kb_miss:
            messages.append({"role": "system", "content": (
                "The knowledge base does NOT contain a clear answer to this question. Say you don't have that detail "
                "(you may mention only what the knowledge base does say) and offer to connect them with a counselor. "
                "Do NOT explain how it generally works or list steps, documents or requirements from general knowledge.")})
        if kb_single_fact:
            messages.append({"role": "system", "content": (
                "No step-by-step, checklist or timeline card fits this question. Answer in one to three sentences using ONLY the "
                "knowledge base text above. If that text does not state the answer, say you don't have that detail and offer to connect "
                "them with a counselor. Do NOT use general knowledge.")})
        if outcome is not None:
            messages.append({"role": "system", "content": outcome.message})
        # Code already showed the card -> the LLM only writes the lead-in (no tools).
        # If nothing could be shown (missing data), keep tools so it can follow the tool's instruction.
        tools = None if (outcome is not None and outcome.block) else EDUCATION_TOOLS

        full_answer = templated or ""
        if templated:
            yield {"type": "token", "data": templated}
        grounding_on = settings.education_grounding_check and detect_language(question) == "en"
        loop_templated: str | None = None
        card_in_loop = False   # only the FIRST result card an LLM-called tool shows in a turn is composed and remembered
        tool_card: tuple[str, dict] | None = None   # that card's intent and args, for the page link
        for _ in range(0 if templated else MAX_TOOL_ITERATIONS):
            await db.commit()  # release the pooler connection before each LLM round-trip

            kwargs = {"tools": tools} if tools else {}
            response = await self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=200, temperature=0.2, stream=True, **kwargs,
            )

            current_text = ""
            tool_calls_data: dict[int, dict] = {}
            async for chunk in response:
                delta = chunk.choices[0].delta
                if delta.content:
                    current_text += delta.content
                    if not grounding_on:
                        yield {"type": "token", "data": delta.content}
                for tc in delta.tool_calls or []:
                    slot = tool_calls_data.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments

            final_text = current_text
            if grounding_on and current_text.strip():
                checked = check_answer(
                    current_text,
                    build_support(chunks, catalog, profile, [b.fallback_text for b in shown], question),
                    catalog, brand_name)
                final_text = checked.text
                if checked.dropped:
                    logger.info("[EDU] grounding dropped=%d kept=%d kinds=%s", checked.dropped, checked.kept, sorted(set(checked.reasons)))
                if checked.empty:
                    final_text = KB_MISS   # nothing in the reply could be backed: the honest answer, with the counselor button
                    if settings.education_compositions and not any(b.type == "quick_chips" for b in shown):
                        counselor = counselor_block(catalog)
                        shown.append(counselor)
                        yield {"type": "ui_block", "block": counselor.model_dump()}
                yield {"type": "token", "data": final_text}

            if not tool_calls_data:
                full_answer = final_text
                break

            calls = [{"id": tool_calls_data[i]["id"], "type": "function",
                      "function": {"name": tool_calls_data[i]["name"], "arguments": tool_calls_data[i]["arguments"]}}
                     for i in sorted(tool_calls_data)]
            messages.append({"role": "assistant", "content": current_text or None, "tool_calls": calls})

            # Several result cards in one reply (e.g. two countries' facts): show them plain. Buttons or a one-line sentence about
            # just one of them would sit in the middle of the others and describe only part of what is on screen.
            several_cards = sum(1 for c in calls if TOOL_TO_INTENT.get(c["function"]["name"]) in RESULT_INTENTS) > 1
            for call in calls:
                tool_name = call["function"]["name"]
                try:
                    tool_args = json.loads(call["function"]["arguments"])
                except ValueError:
                    tool_args = {}
                logger.info("[EDU] tool=%s arg_keys=%s", tool_name, sorted(tool_args) if isinstance(tool_args, dict) else [])

                yield {"type": "tool_call", "name": tool_name, "status": "running"}
                result = execute_education_tool(tool_name, tool_args, profile, catalog)
                yield {"type": "tool_call", "name": tool_name, "status": "done"}
                asked_for_details = False
                if (result.block is None and TOOL_TO_INTENT.get(tool_name) == "recommend_country"
                        and settings.education_template_leadins and (ask := _ask_for_budget(profile, catalog))):
                    asked_for_details = True
                    profile["awaiting"] = "recommend_country"
                    result = ToolOutcome(ask.block, "The student now sees a yearly-budget slider because countries can't be ranked "
                                         "until you know their budget. Say that in one short sentence; do not suggest any country.")

                tool_message = result.message
                if result.block and all(b.block_id != result.block.block_id for b in shown):
                    card_intent = TOOL_TO_INTENT.get(tool_name)
                    if asked_for_details:
                        blocks = [result.block]
                        if can_template:
                            loop_templated = NEEDS_DETAILS
                    elif card_intent in RESULT_INTENTS and several_cards:
                        record_ui_state(profile, card_intent, normalized_args(card_intent, tool_args, catalog))  # the last one stays remembered
                        blocks = [result.block]
                    elif card_intent in RESULT_INTENTS and not card_in_loop:
                        # Same treatment as a card the rules chose: companions, remembered state, a sentence from the card.
                        card_in_loop = True
                        card_args = normalized_args(card_intent, tool_args, catalog)
                        tool_card = (card_intent, card_args)
                        record_ui_state(profile, card_intent, card_args)
                        blocks = compose(card_intent, card_args, result.block, profile, catalog) if settings.education_compositions else [result.block]
                        if len(blocks) > 1:
                            tool_message += (" Related blocks and next-step buttons appear with it; "
                                             "do not list, repeat or describe them.")
                        if can_template:
                            loop_templated = leadin_for(card_intent, card_args, result.block, catalog, brand_name)
                    else:
                        blocks = [result.block]
                    for block in blocks:
                        shown.append(block)
                        yield {"type": "ui_block", "block": block.model_dump()}
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": tool_message})
            if loop_templated and not current_text.strip():
                # the card is on screen with its sentence written by code: no further LLM round trip is needed
                full_answer = loop_templated
                yield {"type": "token", "data": loop_templated}
                break
            full_answer = final_text

        if not full_answer and shown:
            full_answer = next((b.title for b in reversed(shown) if b.title), "")

        # One code-written link to the right Admizz page (never model output): chosen by the card or the topic asked about and
        # the country in context. Added after the grounding check, streamed and saved so a reload shows it too.
        card_intent, card_args = intent if intent else (tool_card or (None, {}))
        if link := link_for_turn(site_id, catalog, profile, question=question, intent=card_intent, intent_args=card_args,
                                 kb_chunks=chunks, kb_miss=kb_miss, understanding=understanding, min_confidence=min_confidence):
            line, url = link
            profile.setdefault("links_shown", []).append(url)
            suffix = ("\n\n" if full_answer else "") + line
            full_answer += suffix
            yield {"type": "token", "data": suffix}

        # Persist the turn: profile (incl. the shown-blocks cache) and the transcript with its blocks.
        await memory.save_profile(customer_id, session_id, profile)
        if full_answer or shown:
            await memory.append_message(customer_id, session_id, "assistant", full_answer,
                                        [b.model_dump() for b in shown])

        yield {"type": "done", "answer": full_answer, "suggestions": [], "sources": [], "profile_progress": progress(profile)}


_education_agent_service: EducationAgentService | None = None


def get_education_agent_service() -> EducationAgentService:
    global _education_agent_service
    if _education_agent_service is None:
        _education_agent_service = EducationAgentService()
    return _education_agent_service
