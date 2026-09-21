"""Code-side explicit-yes gate for booking writes (CLINIC-CONFIRM-EXPLICIT-YES-BRIEF).

A live voice call fired confirm_booking on the filler "हुँ।" — the "only after an
explicit yes" rule existed only in the prompt (llm_prompt_mandate_vs_actual_behavior).
Design: an allow-list, NOT an LLM classifier. A false "not yes" costs one extra
question; a false "yes" is a wrong booking in a production clinic system, so the
gate must be deterministic, zero-latency on the write turn, and unit-testable
exhaustively. A classifier adds latency plus its own eval and can be argued out
of a refusal the same way the prompt was.

Rules: every token must be on the allow-list, at least one must be a strong yes,
any "?" (a question, e.g. "ok?") fails, and any negation token fails outright.
Fillers/back-channels (हुँ, hmm, uh, अँ) are on neither list, so they fail.
Exact-token match matters: गर्दिनु/गर्दिनुस् ("please do") are yes, गर्दिनँ ("I
won't") is a different token and fails — a one-letter flip, so we never fuzzy-match.
When in doubt: re-ask.
"""
import re

# --- Deterministic confirm intent (CLINIC-CONFIRM-INTENT-BRIEF) ---
#
# Live runs showed the same "Yes, please book it." after an identical read-back
# sometimes reaching confirm_booking and sometimes making the model re-run
# prepare_booking instead — and since the F1 net above ends the turn after any
# successful prepare, that re-prepare became a silent stall (same question
# repeated). Which tool the model picks is nondeterministic, so when the
# visitor's whole message is an unambiguous yes to a read-back that is still
# awaiting confirmation, code calls confirm_booking itself.
#
# Deliberately conservative: EVERY token must be on the allow-list and at least
# one must be a strong yes. Any extra word ("but", "change", a number, a new
# date) fails the check and the message goes to the model as before.
_CONFIRM_STRONG = {
    "yes", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed",
    "correct", "right", "book", "proceed",
    "हुन्छ", "हजुर", "हजुरै", "ठीक", "ठिक", "गर्दिनुस्", "गर्दिनु", "गर्नुहोस्", "बुक",
    "ओके", "पक्का", "हो", "जी", "हाँ", "हस्",
    "huncha", "hunchha", "hajur", "hajurai", "thik", "garidinus", "garnus",
    "pakka", "ho", "ya", "has", "haan", "garidinu",
}
# Belt-and-braces: these can never pass even if someone later adds a stem they
# contain to the allow-list.
_CONFIRM_NEGATIONS = {
    "no", "nope", "not", "dont", "don't", "cancel", "wait", "stop",
    "होइन", "नगर्नुस्", "नगर्नु", "गर्दिनँ", "गर्दिन", "नगर", "पर्दैन", "रोक्नुस्",
    "hoina", "nagarnus", "nagarnu", "gardina", "gardinan", "garidina", "pardaina", "nahune", "hudaina",
}
_CONFIRM_FILLER = {
    "please", "pls", "it", "this", "that", "thats", "go", "ahead", "do", "thanks",
    "thank", "you", "is", "the", "a", "now", "for", "me", "so", "and",
    "छ", "गर्नु", "गरि", "दिनुस्", "अनि", "धन्यवाद", "यो", "त",
    "cha", "chha", "ta", "dinus", "garera", "yo", "dhanyabad", "ani",
}
_CONFIRM_TOKEN_SPLIT = re.compile(r"[\s,.;:!?।'\"’\-]+")


def is_clear_confirmation(message: str) -> bool:
    if "?" in (message or "") or "\uff1f" in (message or ""):
        return False  # a question ("ok?", "हो?") is not a yes
    tokens = [t for t in _CONFIRM_TOKEN_SPLIT.split((message or "").lower()) if t]
    if not tokens or len(tokens) > 8:
        return False
    if any(t in _CONFIRM_NEGATIONS for t in tokens):
        return False
    if not all(t in _CONFIRM_STRONG or t in _CONFIRM_FILLER for t in tokens):
        return False
    return any(t in _CONFIRM_STRONG for t in tokens)




is_explicit_yes = is_clear_confirmation
