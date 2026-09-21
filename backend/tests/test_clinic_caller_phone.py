"""CLINIC-CALLER-PHONE-BRIEF: pin the phone_fact_line wording for both branches."""
from app.services.clinic_agent import CLINIC_SYSTEM_PROMPT, _build_phone_fact_line


def test_with_contact_phone_scopes_rule_to_clinic_and_accepts_caller():
    line = _build_phone_fact_line("980-1222339")
    assert "The clinic's own verified phone number is 980-1222339." in line
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


def test_phone_is_clinic_compares_normalized_digits_only():
    from app.services.clinic_tools import phone_is_clinic
    assert phone_is_clinic("+977 980-1222339", "980-1222339") is True
    assert phone_is_clinic("9801222339", "980-1222339") is True
    assert phone_is_clinic("9841540434", "980-1222339") is False
    assert phone_is_clinic("9841540434", None) is False
    assert phone_is_clinic(None, "980-1222339") is False


async def test_prepare_booking_logs_bool_only_no_digits(caplog, monkeypatch):
    import logging
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.services import clinic_tools

    monkeypatch.setattr(clinic_tools, "_prepare_booking", AsyncMock(return_value={"summary": "x"}))
    cfg = SimpleNamespace(contact_phone="980-1222339")
    with caplog.at_level(logging.INFO):
        await clinic_tools.execute_clinic_tool(
            "prepare_booking", {"phone": "9841540434"}, None, None, cfg, "s", "sess", 1)
    line = next(r.getMessage() for r in caplog.records if "status=" in r.getMessage())
    assert "status=ok phone_is_clinic=False" in line
    assert "9841540434" not in line and "1222339" not in line
