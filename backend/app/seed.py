"""Synthetic demo data — 20 fictional dining-hall employees.

All names, emails and availabilities are invented. Nothing here is
a real Sodexo employee or real workplace data. The mix is deliberate:
full-timers and part-timers, a student with class-shaped gaps
(unavailable weekday mornings), an evening-averse parent, and a
supervisor who only works weekdays — the cases a scheduler must
actually handle, and the cases the tests and the NL examples use.
"""
from .config import DAYS

ALL = ["Morning", "Midday", "Evening"]
WEEKDAYS = DAYS[:5]


def _avail(days, shifts=ALL, off=None):
    off = off or {}
    return {d: [s for s in shifts if s not in off.get(d, [])] for d in days}


SEED_EMPLOYEES = [
    {
        "name": "Alex Morgan", "role": "Cook", "email": "alex.morgan@example.edu",
        "max_hours_per_week": 32,
        "availability": _avail(DAYS, off={"Sunday": ["Evening"]}),
        "notes": "Lead cook. Prefers mornings.",
    },
    {
        "name": "Priya Sharma", "role": "Cook", "email": "priya.sharma@example.edu",
        "max_hours_per_week": 28,
        "availability": _avail(DAYS, off={"Saturday": ["Morning"], "Sunday": ["Morning"]}),
        "notes": "Cross-trained on grill and prep.",
    },
    {
        "name": "Jordan Lee", "role": "Server", "email": "jordan.lee@example.edu",
        "max_hours_per_week": 20,
        # Student: classes weekday mornings, free after 11.
        "availability": _avail(WEEKDAYS, shifts=["Midday", "Evening"]) | _avail(["Saturday", "Sunday"]),
        "notes": "Student — no weekday mornings (classes).",
    },
    {
        "name": "Maya Patel", "role": "Server", "email": "maya.patel@example.edu",
        "max_hours_per_week": 24,
        "availability": _avail(DAYS, off={"Friday": ["Evening"], "Saturday": ["Evening"]}),
        "notes": "Prefers fewer evenings.",
    },
    {
        "name": "Sam Carter", "role": "Server", "email": "sam.carter@example.edu",
        "max_hours_per_week": 16,
        "availability": _avail(["Monday", "Wednesday", "Friday", "Saturday", "Sunday"]),
        "notes": "Part-time, three to four days a week.",
    },
    {
        "name": "Taylor Nguyen", "role": "Cashier", "email": "taylor.nguyen@example.edu",
        "max_hours_per_week": 24,
        "availability": _avail(DAYS),
        "notes": "Flexible — good cover for gaps.",
    },
    {
        "name": "Chris Evans", "role": "Cashier", "email": "chris.evans@example.edu",
        "max_hours_per_week": 20,
        "availability": _avail(WEEKDAYS) | _avail(["Saturday"], shifts=["Morning", "Midday"]),
        "notes": "No Sundays.",
    },
    {
        "name": "Riley Brooks", "role": "Dishwasher", "email": "riley.brooks@example.edu",
        "max_hours_per_week": 28,
        "availability": _avail(DAYS, off={"Monday": ["Morning"]}),
        "notes": "Strong closer.",
    },
    {
        "name": "Jamie Fox", "role": "Dishwasher", "email": "jamie.fox@example.edu",
        "max_hours_per_week": 16,
        "availability": _avail(["Tuesday", "Thursday", "Saturday", "Sunday"]),
        "notes": "Weekend-heavy part-timer.",
    },
    {
        "name": "Casey Kim", "role": "Supervisor", "email": "casey.kim@example.edu",
        "max_hours_per_week": 40,
        "availability": _avail(WEEKDAYS, shifts=["Morning", "Midday"]),
        "notes": "Weekday supervisor. No weekends, no evenings.",
    },
    {
        "name": "Dana Wright", "role": "Supervisor", "email": "dana.wright@example.edu",
        "max_hours_per_week": 32,
        "availability": _avail(DAYS, shifts=["Midday", "Evening"]),
        "notes": "Evening supervisor.",
    },
    {
        "name": "Robin Chen", "role": "Server", "email": "robin.chen@example.edu",
        "max_hours_per_week": 20,
        "availability": _avail(DAYS, off={"Wednesday": ALL, "Sunday": ["Evening"]}),
        "notes": "Off Wednesdays.",
    },
    {
        "name": "Noah Patel", "role": "Cook", "email": "noah.patel@example.edu",
        "max_hours_per_week": 24,
        "availability": _avail(DAYS, off={"Tuesday": ["Morning"]}),
        "notes": "Prep cook, weekend mornings.",
    },
    {
        "name": "Emma Wilson", "role": "Server", "email": "emma.wilson@example.edu",
        "max_hours_per_week": 20,
        "availability": _avail(DAYS, shifts=["Midday", "Evening"]),
        "notes": "Student — afternoons and evenings only.",
    },
    {
        "name": "Liam Garcia", "role": "Server", "email": "liam.garcia@example.edu",
        "max_hours_per_week": 16,
        "availability": _avail(["Monday", "Tuesday", "Thursday", "Friday", "Saturday"]),
        "notes": "Part-time.",
    },
    {
        "name": "Ava Thompson", "role": "Cashier", "email": "ava.thompson@example.edu",
        "max_hours_per_week": 20,
        "availability": _avail(DAYS, off={"Sunday": ALL}),
        "notes": "No Sundays.",
    },
    {
        "name": "Ethan Brown", "role": "Dishwasher", "email": "ethan.brown@example.edu",
        "max_hours_per_week": 20,
        "availability": _avail(DAYS, shifts=["Midday", "Evening"]),
        "notes": "Afternoon/evening dishwasher.",
    },
    {
        "name": "Mia Davis", "role": "Server", "email": "mia.davis@example.edu",
        "max_hours_per_week": 20,
        "availability": _avail(DAYS, off={"Monday": ["Evening"], "Thursday": ["Evening"]}),
        "notes": "Prefers day shifts.",
    },
    {
        "name": "Lucas Miller", "role": "Cook", "email": "lucas.miller@example.edu",
        "max_hours_per_week": 20,
        "availability": _avail(WEEKDAYS) | _avail(["Saturday"], shifts=["Morning", "Midday"]),
        "notes": "Weekday cook.",
    },
    {
        "name": "Sophia Reyes", "role": "Supervisor", "email": "sophia.reyes@example.edu",
        "max_hours_per_week": 28,
        "availability": _avail(["Monday", "Wednesday", "Friday", "Saturday", "Sunday"],
                               shifts=["Morning", "Midday"]),
        "notes": "Weekend supervisor cover.",
    },
]


def seed_employees(db):
    """Insert the demo roster if the table is empty. Idempotent."""
    from .models import Employee

    if db.query(Employee).count():
        return 0
    for e in SEED_EMPLOYEES:
        db.add(Employee(**e))
    db.commit()
    return len(SEED_EMPLOYEES)
