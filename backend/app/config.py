"""Configuration from environment variables. Secrets are never hard-coded.

Demo mode is the default: with no LLM key set, the natural-language
assistant uses the built-in rule parser in ``nl_parser.py`` and the
scheduler still works fully. Set OPENAI_API_KEY or ANTHROPIC_API_KEY
in ``.env`` to enable the optional LLM path (see ``ai_assistant.py``).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'shiftpilot.db'}")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").lower()  # auto | openai | anthropic | none
LLM_MODEL = os.getenv("LLM_MODEL", "")
# Week that generated schedules cover. Monday of the demo week.
WEEK_START = os.getenv("WEEK_START", "2026-11-30")

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# (label, start, end) — 4-hour shifts, the unit the dining hall actually rosters.
SHIFTS = [
    ("Morning", "07:00", "11:00"),
    ("Midday", "11:00", "15:00"),
    ("Evening", "15:00", "19:00"),
]
SHIFT_HOURS = 4
ROLES = ["Cook", "Server", "Cashier", "Dishwasher", "Supervisor"]

# Default staffing requirement: how many people of each role per shift.
# A real dining hall needs more servers at lunch; evenings are lighter.
DEFAULT_REQUIREMENTS: dict[str, dict[str, int]] = {
    # Per-day, per-shift headcount. Weekly demand is these numbers x 7
    # = 126 slots; the 20-person demo roster can work ~118 shifts/week
    # (one 4h shift per person per day, capped by max hours), so a good
    # optimiser lands at roughly 85-95% coverage — realistic for a
    # dining hall, and the shortfall is reported, not hidden.
    "Cook": {"Morning": 1, "Midday": 2, "Evening": 1},
    "Server": {"Morning": 2, "Midday": 2, "Evening": 2},
    "Cashier": {"Morning": 1, "Midday": 1, "Evening": 1},
    "Dishwasher": {"Morning": 1, "Midday": 1, "Evening": 1},
    "Supervisor": {"Morning": 1, "Midday": 1, "Evening": 0},
}
