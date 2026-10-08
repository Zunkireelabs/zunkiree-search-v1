"""
Interactive answers built from the tenant's own knowledge base.

For open questions ("what's the process?", "what documents do I need?") the
answer is an interactive component, chosen by the SHAPE of the answer:

    process   -> stepper       (a sequence of steps)
    checklist -> checklist     (things needed / required)
    timeline  -> timeline      (dates, durations, deadlines)
    offerings -> accordion     (services / programs / options)

Consistency: the shape -> component map is fixed, shape detection is
deterministic keyword rules (with a temperature-0 LLM fallback for unusual
phrasing, cached), and the built block is cached per (shape, retrieved
content), so the same question gives the same component with the same content.

Grounding: the LLM only restructures retrieved knowledge-base text into the
component's schema. It must return {"found": false} when the text doesn't
clearly contain the answer, every item is checked against the retrieved text,
and the pages used are attached as `sources`. Single-fact answers ("is it
free?") have no shape and stay plain text.
"""
import hashlib
import json
import logging
import re
from dataclasses import dataclass

from app.schemas.ui_blocks import BlockValidationError, UIBlock, build_block, is_current, upgrade_stored_block

logger = logging.getLogger("zunkiree.education_kb_blocks")


@dataclass(frozen=True)
class ShapeSpec:
    shape: str
    block_type: str
    list_key: str                 # key holding the items, both in the LLM JSON and in the block data
    text_keys: tuple[str, ...]    # item fields that must be traceable to the retrieved text
    min_items: int
    component: str
    json_format: str


SHAPES: dict[str, ShapeSpec] = {s.shape: s for s in [
    ShapeSpec(
        "process", "stepper", "steps", ("title",), 2,
        "a step-by-step process (steps in the order the knowledge base gives them)",
        '{"found": true, "title": "<short noun phrase>", "source_titles": ["<bracketed page titles you used>"], '
        '"steps": [{"title": "<short step name>", "detail": "<one sentence from the knowledge base, or null>"}]}',
    ),
    ShapeSpec(
        "checklist", "checklist", "items", ("label",), 1,
        "a checklist of things the student needs or must prepare",
        '{"found": true, "title": "<short noun phrase>", "source_titles": ["<bracketed page titles you used>"], '
        '"items": [{"label": "<short item>", "note": "<short qualifier from the knowledge base, or null>"}]}',
    ),
    ShapeSpec(
        "timeline", "timeline", "events", ("title", "when"), 2,
        "a timeline of dates, periods or deadlines (copy dates exactly as written)",
        '{"found": true, "title": "<short noun phrase>", "source_titles": ["<bracketed page titles you used>"], '
        '"events": [{"when": "<date or period exactly as written>", "title": "<what happens>", "detail": "<one sentence or null>"}]}',
    ),
    ShapeSpec(
        "offerings", "accordion", "items", ("title",), 1,
        "a list of services, programs or options, each with a short explanation",
        '{"found": true, "title": "<short noun phrase>", "source_titles": ["<bracketed page titles you used>"], '
        '"items": [{"title": "<name>", "summary": "<5-10 words>", "detail": "<1-2 sentences from the knowledge base>"}]}',
    ),
]}

SHAPE_TO_BLOCK = {s.shape: s.block_type for s in SHAPES.values()}

# Shown in the widget's skeleton while the component is being built.
PENDING_LABELS = {
    "process": "Finding the steps…",
    "checklist": "Gathering what you'll need…",
    "timeline": "Looking up the dates…",
    "offerings": "Finding what's available…",
}


def _rx(*patterns: str) -> re.Pattern:
    return re.compile("|".join(patterns), re.I)


# Order matters: first match wins.
_RULES: list[tuple[str, re.Pattern]] = [
    ("process", _rx(r"\bprocess\b", r"\bprocedure\b", r"\bsteps?\b", r"how to apply",
                    r"how (do|can|should|to) (i|we) (apply|get started|start|begin|enrol|enroll|proceed)",
                    r"how does .{0,40} work", r"what happens (after|next|then)", r"\bwalk me through\b")),
    ("checklist", _rx(r"\bdocuments?\b", r"\brequirements?\b", r"\bchecklist\b",
                      r"what (do|should|must) i (need|bring|prepare|submit|have)", r"what.{0,20}(needed|required)")),
    ("timeline", _rx(r"\bdeadlines?\b", r"\btimeline\b", r"\bintake dates?\b", r"how long", r"\bschedule\b", r"by when",
                     r"when (do|does|should|can|is|are).{0,30}(apply|start|begin|intake|open|close)")),
    ("offerings", _rx(r"\bservices?\b", r"what (do|does|can) .{0,30}(offer|provide|help)", r"how (can|do|does) .{0,30}help",
                      r"what can (you|admizz)", r"\boffer(s|ed|ing)?\b", r"\bcourses?\b", r"\bprograms?\b",
                      r"scholarships?", r"what is admizz", r"who are you", r"tell me about (admizz|your)")),
]

_QUESTION_START = re.compile(r"^(what|how|when|where|which|who|why|can|could|do|does|is|are|will|should|tell|explain|list|show|give)\b", re.I)


def classify_shape_rules(question: str) -> str | None:
    for shape, rx in _RULES:
        if rx.search(question):
            return shape
    return None


def looks_like_question(question: str) -> bool:
    q = question.strip()
    return len(q) >= 8 and ("?" in q or bool(_QUESTION_START.match(q)))


_llm_shape_cache: dict[str, str | None] = {}


async def classify_shape(client, model: str, question: str) -> str | None:
    """Deterministic rules first; for unusual phrasing a temperature-0 LLM picks from a fixed list (cached)."""
    shape = classify_shape_rules(question)
    if shape or not looks_like_question(question):
        return shape

    key = " ".join(question.lower().split())
    if key in _llm_shape_cache:
        return _llm_shape_cache[key]

    try:
        resp = await client.chat.completions.create(
            model=model, temperature=0, max_tokens=20,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": (
                    "Classify the student's question by the shape of its ideal answer. Reply JSON {\"shape\": X} with X one of: "
                    "process (a sequence of steps), checklist (a list of things needed), timeline (dates, durations, deadlines), "
                    "offerings (a list of services/programs/options), none (a single fact, yes/no, opinion, chit-chat, "
                    "or a statement about themselves).")},
                {"role": "user", "content": question},
            ],
        )
        picked = json.loads(resp.choices[0].message.content).get("shape")
    except Exception as e:  # classification must never break a turn
        logger.warning("[EDU-KB] shape classification failed: %s", e)
        return None

    result = picked if picked in SHAPES else None
    if len(_llm_shape_cache) > 500:
        _llm_shape_cache.clear()
    _llm_shape_cache[key] = result
    return result


# ---- grounded extraction ----

_STOP = {"the", "and", "for", "with", "your", "you", "our", "are", "that", "this", "from", "have", "has", "will", "can",
         "get", "any", "all", "how", "who", "what", "when", "into", "about", "their", "they", "them", "its"}

_EXTRACT_SYSTEM = """You turn knowledge-base text into structured JSON for an interactive UI component.

Rules:
- Use ONLY information stated in the KNOWLEDGE BASE below. Never add steps, items, dates, numbers, names or details that are not there.
- Keep the knowledge base's own order and wording; shorten, never embellish.
- If the knowledge base does not clearly contain this information, reply exactly {{"found": false}}.
- Scraped pages can separate labels from their values; never pair a number with a label unless the text makes the pairing unmistakable.

Component: {component}
Reply with JSON only, in exactly this format: {json_format}

KNOWLEDGE BASE:
{context}"""


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t not in _STOP}


def _context(chunks: list[dict]) -> str:
    return "\n\n".join(f"[{c.get('source_title') or 'Source'}]\n{c['content']}" for c in chunks)


def cache_key(shape: str, chunks: list[dict]) -> str:
    """Keyed by the BEST-matching passage, not the whole retrieved set: different wordings of the same
    question retrieve slightly different supporting passages but the same top one."""
    return f"kb:{shape}:{hashlib.sha1(chunks[0]['content'].encode()).hexdigest()[:12]}"


def _grounded_items(spec: ShapeSpec, items, corpus: set[str]) -> list[dict]:
    """Drop items whose key text shares nothing with the retrieved text (a cheap guard against invention)."""
    kept = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get(k) or "") for k in spec.text_keys)
        toks = _tokens(text)
        if toks and not (toks & corpus):
            logger.info("[EDU-KB] dropped ungrounded item: %r", text[:60])
            continue
        clean = {k: v for k, v in item.items() if v not in (None, "")}
        for key in ("label", "title"):  # "application form" -> "Application form"
            if isinstance(clean.get(key), str):
                clean[key] = clean[key][:1].upper() + clean[key][1:]
        kept.append(clean)
    return kept


async def extract_block(client, model: str, shape: str, question: str, chunks: list[dict]) -> UIBlock | None:
    """Build the component for `shape` from retrieved chunks, or None if the knowledge base doesn't have it."""
    spec = SHAPES[shape]
    if not chunks:
        return None
    try:
        resp = await client.chat.completions.create(
            model=model, temperature=0, max_tokens=900,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM.format(
                    component=spec.component, json_format=spec.json_format, context=_context(chunks))},
                {"role": "user", "content": question},
            ],
        )
        data = json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning("[EDU-KB] extraction failed: %s", e)
        return None

    if not isinstance(data, dict) or not data.get("found"):
        return None

    corpus = _tokens(" ".join(c["content"] for c in chunks))
    items = _grounded_items(spec, data.get(spec.list_key), corpus)
    if len(items) < spec.min_items:
        return None

    page_titles = {c.get("source_title") or "Source" for c in chunks}
    used = [t for t in (data.get("source_titles") or []) if t in page_titles]
    sources = (used or [chunks[0].get("source_title") or "Source"])[:3]
    title = str(data.get("title") or "").strip()[:80]
    title = (title[:1].upper() + title[1:]) or None  # "admission documents" -> "Admission documents"

    label_key = "label" if "label" in spec.text_keys else "title"
    try:
        return build_block(
            spec.block_type, {spec.list_key: items}, title=title, sources=sources,
            fallback_text=f"{title or 'Answer'}: " + "; ".join(str(i.get(label_key) or i.get("title") or i.get("when")) for i in items) + ".",
        )
    except BlockValidationError as e:
        logger.warning("[EDU-KB] extracted %s block failed validation: %s", shape, e)
        return None


# Shared by every student in this process: the same knowledge-base content gives every student the same
# component (and the second student doesn't pay for another extraction). Persisted per student in
# profile["shown"], so a student also keeps their component across restarts.
_shared_cache: dict[str, dict] = {}


async def kb_block(client, model: str, profile: dict, shape: str, question: str, chunks: list[dict]) -> UIBlock | None:
    """Same shape + same best passage -> the identical component, however the question was worded."""
    if not chunks:
        return None
    key = cache_key(shape, chunks)
    shown = profile.setdefault("shown", {})

    stored = shown.get(key) or _shared_cache.get(key)
    if stored:
        upgraded = upgrade_stored_block(stored["block"])   # an older UI version is upgraded, else rebuilt below
        if is_current(upgraded):
            shown.setdefault(key, stored)
            return UIBlock.model_validate(upgraded)

    block = await extract_block(client, model, shape, question, chunks)
    if block:
        entry = {"hash": "", "inputs": {}, "block": block.model_dump()}
        shown[key] = entry
        if len(_shared_cache) > 500:
            _shared_cache.clear()
        _shared_cache[key] = entry
    return block
