"""SBAL-Z4: the clinic agent introduces itself as "<assistant_name>, <brand_name>'s
AI assistant" on the first turn only, when assistant_name is set. Absent it, today's
behaviour is unchanged."""
from app.services.clinic_agent import CLINIC_SYSTEM_PROMPT, _build_intro_line


def test_assistant_name_set_on_first_turn_introduces_itself():
    line = _build_intro_line("Sammy", "Sami's Brow and Lashes", True)
    assert '"Sammy, Sami\'s Brow and Lashes\'s AI assistant"' in line
    assert "first message of the conversation" in line


def test_assistant_name_absent_is_a_no_op():
    assert _build_intro_line(None, "Sami's Brow and Lashes", True) == ""


def test_assistant_name_set_but_not_first_turn_is_a_no_op():
    assert _build_intro_line("Sammy", "Sami's Brow and Lashes", False) == ""


def test_system_prompt_has_intro_line_placeholder():
    assert "{intro_line}" in CLINIC_SYSTEM_PROMPT
