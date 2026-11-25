"""Plain-text output and the "needs a human" signal for a trusted server caller (EdgeX website chat, channel "text").

The widget shows cards and buttons; a plain text channel cannot. Every block already carries a `fallback_text`, so here the
cards are written into the answer as lines of text. The hand-off signal is set from what the agent already decided
(no knowledge-base answer, or the visitor asked for a person), never by reading the wording of the answer.
"""
import re

TEXT_CHANNEL = "text"

# A visitor asking for a person rather than an answer. Deliberately specific: "counselling" or "counselor fee" alone must not match.
_ASKS_FOR_PERSON = re.compile(
    r"\b(?:"
    r"(?:talk|speak|chat|connect|get\s+in\s+touch|reach)\s+(?:me\s+)?(?:to|with)\s+(?:a|an|the|some|someone|somebody|your)?\s*"
    r"(?:real\s+|live\s+|human\s+)?(?:person|human|counsell?or|agent|advis[eo]r|consultant|representative|staff|team|someone|somebody)"
    r"|(?:call|phone|ring)\s+me"
    r"|(?:need|want|get)\s+(?:a|an|to\s+talk\s+to\s+a)\s*(?:real\s+|live\s+|human\s+)?(?:person|human|counsell?or|agent|advis[eo]r)"
    r"|(?:real|live)\s+(?:person|human)"
    r")\b",
    re.IGNORECASE,
)


def asks_for_person(question: str) -> bool:
    return bool(_ASKS_FOR_PERSON.search(question or ""))


def needs_human_reason(*, question: str, kb_miss: bool, grounding_empty: bool) -> str | None:
    """`asked_for_person` | `out_of_knowledge` | None. Asking for a person wins: it is the clearer instruction."""
    if asks_for_person(question):
        return "asked_for_person"
    if kb_miss or grounding_empty:
        return "out_of_knowledge"
    return None


def blocks_as_text(blocks) -> str:
    """The cards the student would have seen, as plain lines. Buttons-only blocks (next-step chips) are left out: they
    point at things a text chat cannot do."""
    lines = [b.fallback_text.strip() for b in blocks if b.type != "quick_chips" and (b.fallback_text or "").strip()]
    return "\n".join(lines)
