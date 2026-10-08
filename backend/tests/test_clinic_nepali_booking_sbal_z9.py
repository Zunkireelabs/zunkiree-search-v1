"""SBAL-Z9: Nepali booking flow — service binding (F1), spoken-digit phones
and the missing-details loop breaker (F2), localized date/time (F3)."""
import pytest

from app.services import clinic_tools
from app.services.clinic_agent import (
    _build_missing_details_prompt, _ne_time_phrase, _MISSING_PHONE_RETRY_BY_LANG,
)
from app.services.clinic_tools import _resolve_session_service, to_e164

TREATMENTS = [
    {"id": "t-lash", "name": "Lash Lift"},
    {"id": "t-brow", "name": "Brow Lamination"},
    {"id": "t-facial", "name": "Facial Basic"},
    {"id": "t-facial2", "name": "Facial Deluxe"},
]


@pytest.mark.parametrize("raw", [
    "नाइन एट फोर वन फाइभ फोर जिरो फोर थ्री फोर",
    "नौ आठ चार एक पाँच चार शून्य चार तीन चार",
    "nine eight four one five four zero four three four",
    "मेरो नम्बर छ नौ आठ चार एक पाँच चार शून्य चार तीन चार",
    "९८४१५४०४३४",
    "9841540434",
])
def test_phone_words_fold_to_e164(raw):
    assert to_e164(raw) == "+9779841540434"


@pytest.mark.parametrize("raw", ["", "abc", "नाइन एट", "मेरो नम्बर छैन"])
def test_non_phone_text_stays_invalid(raw):
    assert to_e164(raw) is None


def test_double_digit_word():
    assert to_e164("nine eight four one five four double zero three four") == "+9779841540034"


def test_service_binds_then_survives_devanagari_echo():
    sid = "z9-bind"
    clinic_tools._SESSION_STATE.pop(sid, None)
    t, _ = _resolve_session_service(TREATMENTS, "Lash Lift", sid)
    assert t["id"] == "t-lash"
    for echo in ("ल्यास लिफ्ट", "भोलिको", ""):
        t, amb = _resolve_session_service(TREATMENTS, echo, sid)
        assert t["id"] == "t-lash" and not amb


def test_different_service_still_wins_and_rebinds():
    sid = "z9-rebind"
    clinic_tools._SESSION_STATE.pop(sid, None)
    _resolve_session_service(TREATMENTS, "Lash Lift", sid)
    t, _ = _resolve_session_service(TREATMENTS, "brow lamination", sid)
    assert t["id"] == "t-brow"
    t, _ = _resolve_session_service(TREATMENTS, "ब्रो", sid)
    assert t["id"] == "t-brow"


def test_ambiguous_latin_string_not_swallowed_by_bound():
    sid = "z9-amb"
    clinic_tools._SESSION_STATE.pop(sid, None)
    _resolve_session_service(TREATMENTS, "Lash Lift", sid)
    t, amb = _resolve_session_service(TREATMENTS, "facial", sid)
    assert t is None and len(amb) == 2


def test_no_bound_service_behaves_like_before():
    sid = "z9-none"
    clinic_tools._SESSION_STATE.pop(sid, None)
    assert _resolve_session_service(TREATMENTS, "भोलिको", sid) == (None, [])
    assert _resolve_session_service(TREATMENTS, "Lash Lift", sid)[0]["id"] == "t-lash"


INFO = {"error": "INVALID_PHONE", "service_name": "Lash Lift", "date": "2026-10-09", "time": "10:00"}


def test_missing_details_ask_escalates_never_repeats():
    p1 = _build_missing_details_prompt(INFO, "ne_devanagari", attempt=1)
    p2 = _build_missing_details_prompt(INFO, "ne_devanagari", attempt=2, contact_phone="01-4000000")
    p3 = _build_missing_details_prompt(INFO, "ne_devanagari", attempt=3, contact_phone="01-4000000")
    p4 = _build_missing_details_prompt(INFO, "ne_devanagari", attempt=4, contact_phone="01-4000000")
    assert len({p1, p2, p3}) == 3
    assert p2 == _MISSING_PHONE_RETRY_BY_LANG["ne_devanagari"] and "एक-एक गरी" in p2
    assert "01-4000000" in p3 and p3 == p4


def test_devanagari_prompt_is_localized_without_double_baje():
    p = _build_missing_details_prompt(INFO, "ne_devanagari", attempt=1)
    assert "बजे बजे" not in p and "बिहान १० बजे" in p
    assert "October" not in p and "अक्टोबर" in p and "Lash Lift" in p


def test_ne_time_phrase():
    assert _ne_time_phrase("14:30") == "दिउँसो २:३० बजे"
    assert _ne_time_phrase("garbage") == "garbage"


def test_bump_escalates_on_repeat_not_on_first_ask():
    sid = "z9-bump"
    clinic_tools._SESSION_STATE.pop(sid, None)
    assert clinic_tools.bump_missing_asks(sid, repeat=False) == 1
    assert clinic_tools.bump_missing_asks(sid, repeat=False) == 1  # different slot, no details
    assert clinic_tools.bump_missing_asks(sid, repeat=True) == 2
    assert clinic_tools.bump_missing_asks(sid, repeat=True) == 3


def test_invalid_name_loop_reaches_retry_then_handoff():
    from app.services.clinic_agent import _MISSING_NAME_RETRY_BY_LANG
    info = {**INFO, "error": "INVALID_NAME"}
    sid = "z9-name"
    clinic_tools._SESSION_STATE.pop(sid, None)
    prompts = [
        _build_missing_details_prompt(info, "ne_devanagari", clinic_tools.bump_missing_asks(sid, repeat=r), "01-4000000")
        for r in (False, True, True, True)
    ]
    assert prompts[1] == _MISSING_NAME_RETRY_BY_LANG["ne_devanagari"]
    assert "01-4000000" in prompts[2] and prompts[2] == prompts[3]
    assert len(set(prompts[:3])) == 3


def test_devanagari_mid_flow_service_change_keeps_bound_service(caplog):
    """Documented limit (post-demo re-land per brief §7): a switch stated in
    Devanagari ("होइन, ब्रो लामिनेसन") is non-Latin and matches nothing, so
    the bound service is kept (logged) and the read-back names it — the
    caller hears it and can correct. Pinned so the limit is not silent."""
    import logging
    sid = "z9-switch"
    clinic_tools._SESSION_STATE.pop(sid, None)
    _resolve_session_service(TREATMENTS, "Lash Lift", sid)
    with caplog.at_level(logging.INFO, logger="zunkiree.clinic_tools"):
        t, _ = _resolve_session_service(TREATMENTS, "ब्रो लामिनेसन", sid)
    assert t["id"] == "t-lash"
    assert "service_rebound_to_session" in caplog.text
    # A Latin-stated switch still wins.
    assert _resolve_session_service(TREATMENTS, "Brow Lamination", sid)[0]["id"] == "t-brow"
