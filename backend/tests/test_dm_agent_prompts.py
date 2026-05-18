"""
IG-2 regression guard: DM_ECOMMERCE_SYSTEM_PROMPT must enforce always-English output.

The two-pass design (agent in English, translation pass localizes) requires the
agent prompt to explicitly mandate English. Without it, the agent infers output
language from conversation history and sticks to Nepali after any Nepali turn.

IG-8 regression guards (appended): quantity directive and SIZING rule tightening
that prevent typed add-to-cart from inflating quantity from 1 → 2.
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


# ---------------------------------------------------------------------------
# IG-8 guards — quantity inflation prevention
# ---------------------------------------------------------------------------

def test_dm_ecommerce_prompt_has_quantity_directive():
    """QUANTITY: rule must be present — prevents LLM from inferring purchase qty from carousel count."""
    assert "QUANTITY:" in DM_ECOMMERCE_SYSTEM_PROMPT


def test_dm_ecommerce_prompt_sizing_forbids_double_add():
    """SIZING rule must tell the agent not to fire add_to_cart twice for typed-add requests."""
    assert "Do NOT fire add_to_cart a second time" in DM_ECOMMERCE_SYSTEM_PROMPT


def test_dm_ecommerce_prompt_sizing_references_products_shown():
    """SIZING rule must reference [products_shown] (the new manifest format from IG-6)."""
    assert "[products_shown]" in DM_ECOMMERCE_SYSTEM_PROMPT


def test_dm_ecommerce_prompt_sizing_no_old_product_id_marker():
    """SIZING rule must NOT reference the obsolete [product_id: marker (pre-IG-6 format)."""
    assert "[product_id:" not in DM_ECOMMERCE_SYSTEM_PROMPT


def test_dm_ecommerce_prompt_no_comma_list_manifest_example():
    """
    The prompt must not describe the manifest as a comma-separated id=Name list.
    That phrasing was the H4 vector — the LLM read '2 products listed' as quantity=2.
    """
    assert "id1=Name1, id2=Name2" not in DM_ECOMMERCE_SYSTEM_PROMPT
