"""
Pure availability logic for the ClinicMD clinic agent, ported EXACTLY from
clinic-md's DateTimeSelection.jsx + customer-booking-flow/utils/availability.js.

Do NOT "improve" on the web flow's rules (e.g. do not switch to
branches.open_time/close_time) — the agent must never offer a slot the
public booking page would show as unavailable.
"""
from datetime import date, datetime

START_HOUR = 10
END_HOUR = 20
STEP_MINUTES = 30
DEFAULT_DURATION_MINUTES = 60
MAX_DAYS_AHEAD = 30


def parse_hhmm_to_minutes(value: str) -> int:
    """'16:05' or '16:05:00' -> 965."""
    parts = value.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def minutes_to_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def floor_to_step(minutes: int, step: int = STEP_MINUTES) -> int:
    return (minutes // step) * step


def get_chair_capacity(chair: dict) -> int:
    """Null/<1 capacity treated as 1 (matches getChairCapacity in api.js)."""
    cap = chair.get("capacity")
    if cap is None or cap < 1:
        return 1
    return cap


def build_occupancy(bookings: list[dict]) -> dict[tuple[str, int], int]:
    """
    bookings: [{"chair_id": str|None, "start_time": "HH:MM[:SS]", "duration_minutes": int}]

    For each booking, bucket [floor(start/30)*30, start+duration) into 30-min
    slots per chair. Bookings with no chair_id are ignored (can't attribute
    occupancy to a specific chair).
    """
    occupancy: dict[tuple[str, int], int] = {}
    for booking in bookings:
        chair_id = booking.get("chair_id")
        if not chair_id:
            continue
        start_minutes = parse_hhmm_to_minutes(booking["start_time"])
        duration = booking.get("duration_minutes") or DEFAULT_DURATION_MINUTES
        end_minutes = start_minutes + duration
        bucket = floor_to_step(start_minutes)
        while bucket < end_minutes:
            key = (chair_id, bucket)
            occupancy[key] = occupancy.get(key, 0) + 1
            bucket += STEP_MINUTES
    return occupancy


def candidate_starts(duration_minutes: int) -> list[int]:
    """Grid-aligned start minutes-of-day valid for the given duration."""
    starts = []
    end_limit = END_HOUR * 60
    m = START_HOUR * 60
    while m + duration_minutes <= end_limit:
        starts.append(m)
        m += STEP_MINUTES
    return starts


def find_available_chair(
    start_minutes: int,
    duration_minutes: int,
    chairs: list[dict],
    occupancy: dict[tuple[str, int], int],
) -> dict | None:
    """First active chair with remaining capacity across the whole slot span."""
    end_minutes = start_minutes + duration_minutes
    for chair in chairs:
        chair_id = chair["id"]
        capacity = get_chair_capacity(chair)
        offset = floor_to_step(start_minutes)
        fits = True
        while offset < end_minutes:
            if occupancy.get((chair_id, offset), 0) >= capacity:
                fits = False
                break
            offset += STEP_MINUTES
        if fits:
            return chair
    return None


def is_slot_available(
    start_minutes: int,
    duration_minutes: int,
    chairs: list[dict],
    occupancy: dict[tuple[str, int], int],
) -> bool:
    return find_available_chair(start_minutes, duration_minutes, chairs, occupancy) is not None


def available_slots_for_date(
    target_date: date,
    duration_minutes: int,
    chairs: list[dict],
    bookings: list[dict],
    now_npt: datetime,
    limit: int | None = None,
) -> list[str]:
    """Available 'HH:MM' start times on target_date, past-cutoff applied if target_date is today."""
    occupancy = build_occupancy(bookings)
    is_today = target_date == now_npt.date()
    now_minutes = now_npt.hour * 60 + now_npt.minute
    results = []
    for start in candidate_starts(duration_minutes):
        if is_today and start <= now_minutes:
            continue
        if is_slot_available(start, duration_minutes, chairs, occupancy):
            results.append(minutes_to_hhmm(start))
            if limit is not None and len(results) >= limit:
                break
    return results
