from app.conflicts import analytics, detect_conflicts
from app.seed import SEED_EMPLOYEES


def _emps():
    return [{"name": e["name"], "role": e["role"],
             "max_hours_per_week": e["max_hours_per_week"],
             "availability": e["availability"]} for e in SEED_EMPLOYEES]


def test_understaffing_detected_on_empty_schedule():
    conflicts = detect_conflicts(_emps(), [])
    assert any(c["type"] == "understaffed" for c in conflicts)


def test_overtime_detected():
    emp = _emps()[0]  # Alex, max 32h
    assignments = [{"employee_name": emp["name"], "role": "Cook", "day": d, "shift": "Morning"}
                   for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                             "Saturday", "Sunday", "Monday", "Tuesday"]]
    # 9 shifts x 4h = 36h > Alex's 32h max (duplicates also double-book;
    # overtime is the check here).
    conflicts = detect_conflicts(_emps(), assignments)
    assert any(c["type"] == "overtime" for c in conflicts)


def test_double_booking_detected():
    a = [{"employee_name": "Alex Morgan", "role": "Cook", "day": "Monday", "shift": "Morning"},
         {"employee_name": "Alex Morgan", "role": "Cook", "day": "Monday", "shift": "Evening"}]
    assert any(c["type"] == "double_booked" for c in detect_conflicts(_emps(), a))


def test_analytics_counts_hours():
    a = [{"employee_name": "Alex Morgan", "role": "Cook", "day": "Monday", "shift": "Morning"},
         {"employee_name": "Alex Morgan", "role": "Cook", "day": "Tuesday", "shift": "Morning"}]
    out = analytics(_emps(), a)
    assert out["total_hours"] == 8
    assert out["hours_per_employee"][0]["name"] == "Alex Morgan"
