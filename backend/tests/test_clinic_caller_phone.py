"""CLINIC-CALLER-PHONE-BRIEF: pin the phone_fact_line wording for both branches."""
from app.services.clinic_agent import CLINIC_SYSTEM_PROMPT, _build_phone_fact_line


def test_with_contact_phone_scopes_rule_to_clinic_and_accepts_caller():
    line = _build_phone_fact_line("980-1222339")
    assert "The clinic's own phone number is 980-1222339." in line
    assert "give only this one — never alter or invent digits" in line
    assert "about the clinic's number only" in line
    assert "accept whatever number they give you" in line
    assert "never ask them for the clinic's number" in line
    assert "ONLY phone number you may state" not in line


def test_without_contact_phone_states_no_number_but_accepts_caller():
    line = _build_phone_fact_line(None)
    assert "WITHOUT stating any phone number" in line
    assert "accept whatever number they give you" in line
    assert not any(ch.isdigit() for ch in line)


def test_booking_section_names_phone_as_visitors_own():
    assert "phone — the visitor's own contact number" in CLINIC_SYSTEM_PROMPT
