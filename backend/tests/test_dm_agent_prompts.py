"""
IG-2 regression guard: DM_ECOMMERCE_SYSTEM_PROMPT must enforce always-English output.

The two-pass design (agent in English, translation pass localizes) requires the
agent prompt to explicitly mandate English. Without it, the agent infers output
language from conversation history and sticks to Nepali after any Nepali turn.
"""
from app.services.chatbot_query import DM_ECOMMERCE_SYSTEM_PROMPT


def test_dm_ecommerce_prompt_enforces_english_output():
    """Agent prompt must explicitly require English — the translation layer handles localization."""
    assert "ALWAYS write your reply in plain English" in DM_ECOMMERCE_SYSTEM_PROMPT


def test_dm_ecommerce_prompt_forbids_language_switching():
    """Agent must be explicitly told not to switch languages — catches future edits that soften the rule."""
    assert "Do NOT switch to Nepali" in DM_ECOMMERCE_SYSTEM_PROMPT


def test_dm_ecommerce_prompt_no_ambiguous_customer_language_directive():
    """'in the customer's language' is the phrasing that caused IG-2 — must not reappear."""
    assert "in the customer's language" not in DM_ECOMMERCE_SYSTEM_PROMPT


def test_dm_ecommerce_prompt_no_standalone_nepali_pronoun_guidance():
    """Nepali pronoun rules belong in TRANSLATION_SYSTEM_PROMPT only, not in the agent prompt."""
    from app.services.chatbot_query import TRANSLATION_SYSTEM_PROMPT
    # Pronoun guidance must live in the translation prompt (it does)
    assert "tapai" in TRANSLATION_SYSTEM_PROMPT
    # And must NOT appear as a standalone rule block in the agent prompt
    # (it's acceptable in a "Do NOT switch" context — we check the former flag instead)
    assert "NEPALI PRONOUNS (when replying in Romanized Nepali)" not in DM_ECOMMERCE_SYSTEM_PROMPT
