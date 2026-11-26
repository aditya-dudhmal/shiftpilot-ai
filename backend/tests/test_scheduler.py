"""Scheduler tests: hard constraints must never be violated."""
from app.config import DAYS
from app.scheduler import generate_schedule
from app.seed import SEED_EMPLOYEES


def _emps():
    return [{"name": e["name"], "role": e["role"],
             "max_hours_per_week": e["max_hours_per_week"],
             "availability": e["availability"]} for e in SEED_EMPLOYEES]


def test_generate_respects_availability_and_max_hours():
    result = generate_schedule(_emps())
    assert result["assignments"], "scheduler produced no assignments"
    by_emp = {}
    for a in result["assignments"]:
        emp = next(e for e in _emps() if e["name"] == a["employee_name"])
        assert a["shift"] in emp["availability"].get(a["day"], []), f"{a} violates availability"
        by_emp.setdefault(a["employee_name"], []).append(a)
    for name, shifts in by_emp.items():
        emp = next(e for e in _emps() if e["name"] == name)
        assert len(shifts) * 4 <= emp["max_hours_per_week"], f"{name} over max hours"
        days = [s["day"] for s in shifts]
        assert len(days) == len(set(days)), f"{name} double-booked on a day"


def test_generate_coverage_is_high():
    result = generate_schedule(_emps())
    # Weekly demand is 126 slots; the 20-person roster can work ~118
    # shifts, so 75%+ is the bar for this deliberately tight roster.
    assert result["coverage"] >= 0.75, f"coverage too low: {result['coverage']}"


def test_day_off_constraint_is_honoured():
    result = generate_schedule(_emps(), constraints=[
        {"kind": "day_off", "employee_name": "Maya Patel", "payload": {"day": "Friday"}}])
    assert not [a for a in result["assignments"]
                if a["employee_name"] == "Maya Patel" and a["day"] == "Friday"]


def test_evening_cap_constraint_is_honoured():
    result = generate_schedule(_emps(), constraints=[
        {"kind": "limit_evening_shifts", "employee_name": "Alex Morgan", "payload": {"max": 1}}])
    evenings = [a for a in result["assignments"]
                if a["employee_name"] == "Alex Morgan" and a["shift"] == "Evening"]
    assert len(evenings) <= 1


def test_empty_roster_returns_no_assignments():
    result = generate_schedule([])
    assert result["assignments"] == [] and result["status"] == "no-employees"
