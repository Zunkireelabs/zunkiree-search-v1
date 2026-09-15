"""
Availability port fixtures per ZUNKIREE-CLINIC-AGENT-BRIEF §4a/§7:
overlapping bookings, off-grid start (16:05), multi-slot treatment,
capacity-2 chair, today-past cutoff in NPT.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.clinic_availability import (
    available_slots_for_date,
    build_occupancy,
    candidate_starts,
    find_available_chair,
    get_chair_capacity,
    is_slot_available,
    minutes_to_hhmm,
    parse_hhmm_to_minutes,
)

NPT = ZoneInfo("Asia/Kathmandu")


def test_parse_and_format_roundtrip():
    assert parse_hhmm_to_minutes("16:05") == 965
    assert parse_hhmm_to_minutes("16:05:00") == 965
    assert minutes_to_hhmm(965) == "16:05"
    assert minutes_to_hhmm(600) == "10:00"


def test_candidate_starts_respects_grid_and_duration():
    # 60-min treatment: last valid start is 19:00 (19:00+60=20:00)
    starts = candidate_starts(60)
    assert minutes_to_hhmm(starts[0]) == "10:00"
    assert minutes_to_hhmm(starts[-1]) == "19:00"
    assert all(s % 30 == 0 for s in starts)

    # 90-min treatment: last valid start is 18:30 (18:30+90=20:00)
    starts_90 = candidate_starts(90)
    assert minutes_to_hhmm(starts_90[-1]) == "18:30"


def test_chair_capacity_null_or_below_one_treated_as_one():
    assert get_chair_capacity({"capacity": None}) == 1
    assert get_chair_capacity({"capacity": 0}) == 1
    assert get_chair_capacity({"capacity": -1}) == 1
    assert get_chair_capacity({"capacity": 3}) == 3


def test_off_grid_booking_buckets_floor_to_30min_grid():
    # 16:05-16:35 spans two 30-min buckets: floor(965/30)*30=960 (16:00) and
    # 990 (16:30), since the booking's end (995) falls inside the second bucket.
    bookings = [{"chair_id": "c1", "start_time": "16:05", "duration_minutes": 30}]
    occ = build_occupancy(bookings)
    assert occ[("c1", 960)] == 1
    assert occ[("c1", 990)] == 1
    assert ("c1", 1020) not in occ


def test_multi_slot_treatment_occupies_multiple_buckets():
    bookings = [{"chair_id": "c1", "start_time": "10:00", "duration_minutes": 90}]
    occ = build_occupancy(bookings)
    assert occ[("c1", 600)] == 1  # 10:00
    assert occ[("c1", 630)] == 1  # 10:30
    assert occ[("c1", 660)] == 1  # 11:00
    assert ("c1", 690) not in occ  # 11:30 not occupied


def test_overlapping_bookings_increment_same_bucket():
    bookings = [
        {"chair_id": "c1", "start_time": "10:00", "duration_minutes": 30},
        {"chair_id": "c1", "start_time": "10:15", "duration_minutes": 30},
    ]
    occ = build_occupancy(bookings)
    assert occ[("c1", 600)] == 2


def test_capacity_2_chair_available_until_two_overlaps():
    chairs = [{"id": "c1", "name": "Chair 1", "capacity": 2}]
    bookings = [{"chair_id": "c1", "start_time": "10:00", "duration_minutes": 30}]
    occ = build_occupancy(bookings)
    # One booking already in; capacity 2 means still available
    assert is_slot_available(600, 30, chairs, occ) is True

    bookings_full = bookings + [{"chair_id": "c1", "start_time": "10:00", "duration_minutes": 30}]
    occ_full = build_occupancy(bookings_full)
    assert is_slot_available(600, 30, chairs, occ_full) is False


def test_find_available_chair_skips_full_chairs():
    chairs = [
        {"id": "full", "name": "Full Chair", "capacity": 1},
        {"id": "open", "name": "Open Chair", "capacity": 1},
    ]
    bookings = [{"chair_id": "full", "start_time": "10:00", "duration_minutes": 30}]
    occ = build_occupancy(bookings)
    chosen = find_available_chair(600, 30, chairs, occ)
    assert chosen["id"] == "open"


def test_no_chair_id_booking_is_ignored_for_occupancy():
    bookings = [{"chair_id": None, "start_time": "10:00", "duration_minutes": 30}]
    occ = build_occupancy(bookings)
    assert occ == {}


def test_today_past_slots_excluded_in_npt():
    chairs = [{"id": "c1", "name": "Chair 1", "capacity": 1}]
    today = date(2026, 9, 15)
    now_npt = datetime(2026, 9, 15, 14, 30, tzinfo=NPT)  # 14:30 NPT
    slots = available_slots_for_date(today, 60, chairs, [], now_npt)
    assert "10:00" not in slots
    assert "14:00" not in slots  # 14:00+60 > 14:30 start cutoff too, but 14:00 <= 14:30
    assert "14:30" not in slots  # exactly now -> unavailable (start <= now)
    assert "15:00" in slots


def test_future_date_ignores_past_cutoff():
    chairs = [{"id": "c1", "name": "Chair 1", "capacity": 1}]
    tomorrow = date(2026, 9, 16)
    now_npt = datetime(2026, 9, 15, 23, 0, tzinfo=NPT)
    slots = available_slots_for_date(tomorrow, 60, chairs, [], now_npt)
    assert "10:00" in slots


def test_available_slots_respects_limit():
    chairs = [{"id": "c1", "name": "Chair 1", "capacity": 1}]
    today = date(2026, 9, 15)
    now_npt = datetime(2026, 9, 15, 0, 0, tzinfo=NPT)
    slots = available_slots_for_date(today, 60, chairs, [], now_npt, limit=2)
    assert len(slots) == 2
