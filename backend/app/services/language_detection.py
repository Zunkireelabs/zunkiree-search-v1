"""
Language detection for Zunkiree chatbot DM messages.

Heuristic-based — no LLM, no HTTP call, ~0ms.
Returns: "en" | "ne_romanized" | "ne_devanagari" | "mixed_ne_en"
"""
import re

ROMANIZED_NEPALI_SIGNALS = {
    # Verb conjugations / copulas
    "chha", "chhu", "chhan", "thiyo", "huncha", "garnus", "garna",
    "garchu", "garchhu", "dincha", "milcha", "pardaina",
    # Pronouns / possessives
    "tapai", "tapailai", "hami", "timro", "mero", "malai", "ma",
    # Imperative / directional verbs
    "dekhau", "dekhaunos", "dekhaununa", "hernu", "herna",
    # Question words
    "kati", "kasto", "kasari", "kaha", "kun",
    # Common particles / connectors / copulas
    "cha", "ho", "haina", "ra", "ani", "tara", "pani", "haru",
    # Time words
    "aaja", "bholi", "pachi", "aghi",
}


def detect_language(text: str) -> str:
    """
    Returns: "en" | "ne_romanized" | "ne_devanagari" | "mixed_ne_en"
    Fast heuristic — no LLM, no HTTP call.
    """
    # Devanagari Unicode block: U+0900–U+097F
    if any('ऀ' <= c <= 'ॿ' for c in text):
        return "ne_devanagari"

    # Strip punctuation so "cha?" and "cha" both match
    words = set(re.sub(r"[^\w\s]", "", text.lower()).split())
    nepali_signal_count = len(words & ROMANIZED_NEPALI_SIGNALS)

    if nepali_signal_count == 0:
        return "en"
    if nepali_signal_count >= 2:
        return "ne_romanized"
    # Exactly 1 signal word alongside other words → treat as mixed
    return "mixed_ne_en"
