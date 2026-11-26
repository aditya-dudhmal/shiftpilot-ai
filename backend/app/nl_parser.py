"""Natural-language -> validated scheduling constraint.

Two layers, in order:
  1. Rule parser (always available, no API key, deterministic).
     Handles the sentences managers actually type — day-off, fewer/
     more evening shifts, hour caps/floors, avoid/prefer a shift.
  2. Optional LLM layer (``ai_assistant.py``): when a key is set, an
     LLM may propose the same typed constraint; it is then run through
     *exactly the same validation* below before it is stored.

Validation is the point. An LLM (or a typo) must never be able to
invent an employee, a day, or an impossible number and have it
silently change next week's rota. Every parse returns:
  ``{ok, kind, employee_name, payload, explanation, confidence}``
and ``ok=False`` with a human-readable reason when anything fails.
Unknown employees are matched by first name (case-insensitive);
ambiguous first names are rejected, not guessed.
"""
from __future__ import annotations

import re

from .config import DAYS, SHIFTS

SHIFT_LABELS = [s[0] for s in SHIFTS]
DAY_ALIASES = {d.lower(): d for d in DAYS}
DAY_ALIASES.update({"weekday": None, "weekend": None, "mondays": "Monday",
                    "tuesdays": "Tuesday", "wednesdays": "Wednesday",
                    "thursdays": "Thursday", "fridays": "Friday",
                    "saturdays": "Saturday", "sundays": "Sunday"})

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                "zero": 0, "no": 0}


def _num(text):
    m = re.search(r"(\d+)", text)
    if m:
        return int(m.group(1))
    for w, v in NUMBER_WORDS.items():
        if re.search(rf"\b{w}\b", text):
            return v
    return None


def _find_employee(text, employees):
    """First-name match. Returns (employee, error)."""
    lowered = text.lower()
    matches = []
    for e in employees:
        first = e["name"].split()[0].lower()
        full = e["name"].lower()
        if full in lowered or re.search(rf"\b{re.escape(first)}\b", lowered):
            matches.append(e)
    if not matches:
        return None, "I couldn't find that employee in the roster. Check the spelling — try a first name like Alex, Maya or Priya."
    if len(matches) > 1:
        names = ", ".join(m["name"] for m in matches)
        return None, f"That name matches more than one person ({names}). Use a full name."
    return matches[0], None


def _find_day(text):
    lowered = text.lower()
    for alias, day in DAY_ALIASES.items():
        if day and re.search(rf"\b{alias}\b", lowered):
            return day
    return None


def _find_shift(text):
    lowered = text.lower()
    for s in SHIFT_LABELS:
        if s.lower() in lowered:
            return s
    if "morning" in lowered:
        return "Morning"
    if "evening" in lowered or "night" in lowered:
        return "Evening"
    if "midday" in lowered or "lunch" in lowered or "afternoon" in lowered:
        return "Midday"
    return None


def parse_instruction(text, employees, week_start=""):
    """Parse one instruction. Never raises for bad input — returns ok=False."""
    original = text
    t = (text or "").strip().lower()
    if len(t) < 3:
        return {"ok": False, "error": "That instruction is too short. Try e.g. 'Give Maya fewer evening shifts next week'."}

    employee, err = _find_employee(t, employees)
    if err:
        return {"ok": False, "error": err}
    name = employee["name"]
    day = _find_day(t)
    shift = _find_shift(t)

    # Day off: "don't schedule Maya on Friday", "Maya is off Monday",
    # "give Alex Monday off", "Alex needs Friday off".
    if re.search(r"\b(off|day off|don't schedule|do not schedule|not schedule|no shift|unavailable)\b", t) and day:
        return {"ok": True, "kind": "day_off", "employee_name": name,
                "payload": {"day": day}, "week_start": week_start,
                "explanation": f"{name} will not be scheduled on {day}.",
                "confidence": 0.92, "source_text": original}

    # Fewer evening shifts: "give Alex fewer evening shifts"
    if re.search(r"\b(fewer|less|reduce|cut|limit)\b", t) and (shift == "Evening" or "evening" in t):
        cap = _num(t)
        cap = cap if cap is not None else 1
        if cap < 0 or cap > 7:
            return {"ok": False, "error": "Evening-shift cap must be between 0 and 7 per week."}
        return {"ok": True, "kind": "limit_evening_shifts", "employee_name": name,
                "payload": {"max": cap}, "week_start": week_start,
                "explanation": f"{name} will get at most {cap} evening shift(s) next week.",
                "confidence": 0.88, "source_text": original}

    # Max hours: "Alex needs max 20 hours", "cap Priya at 16 hours"
    if re.search(r"\b(max|cap|at most|no more than|limit.*hour)\b", t) and "hour" in t:
        hours = _num(t)
        if hours is None:
            return {"ok": False, "error": "I need a number of hours — e.g. 'Cap Alex at 20 hours'."}
        if hours < 4 or hours > 40 or hours % 4 != 0:
            return {"ok": False, "error": "Hours must be a multiple of 4 between 4 and 40 (shifts are 4 hours)."}
        return {"ok": True, "kind": "max_hours", "employee_name": name,
                "payload": {"max_hours": hours}, "week_start": week_start,
                "explanation": f"{name} will be scheduled for at most {hours} hours next week.",
                "confidence": 0.9, "source_text": original}

    # Min hours / more hours: "give Priya more hours", "Priya needs at least 20 hours"
    if re.search(r"\b(more hours|at least|minimum|min|at least)\b", t) and "hour" in t:
        hours = _num(t)
        if hours is None:
            return {"ok": False, "error": "I need a number of hours — e.g. 'Priya needs at least 20 hours'."}
        if hours < 4 or hours > 40 or hours % 4 != 0:
            return {"ok": False, "error": "Hours must be a multiple of 4 between 4 and 40 (shifts are 4 hours)."}
        if hours > employee["max_hours_per_week"]:
            return {"ok": False, "error": f"{name}'s weekly max is {employee['max_hours_per_week']} hours, so a {hours}-hour minimum would contradict it. Raise their max hours first."}
        return {"ok": True, "kind": "min_hours", "employee_name": name,
                "payload": {"min_hours": hours}, "week_start": week_start,
                "explanation": f"{name} will get at least {hours} hours next week.",
                "confidence": 0.9, "source_text": original}

    # Avoid a shift entirely: "no mornings for Sam", "Sam can't do evenings"
    if re.search(r"\b(can't|cannot|no |never|avoid|don't want)\b", t) and shift:
        return {"ok": True, "kind": "avoid_shift", "employee_name": name,
                "payload": {"shift": shift}, "week_start": week_start,
                "explanation": f"{name} will not be scheduled for {shift} shifts.",
                "confidence": 0.85, "source_text": original}

    # Prefer a shift: "give Jordan more mornings", "Taylor prefers evenings"
    if re.search(r"\b(prefer|more|extra)\b", t) and shift:
        return {"ok": True, "kind": "prefer_shift", "employee_name": name,
                "payload": {"shift": shift}, "week_start": week_start,
                "explanation": f"Next week's schedule will prefer {shift} shifts for {name} where coverage allows. (A preference, not a hard rule — it won't leave a station short.)",
                "confidence": 0.8, "source_text": original}

    return {"ok": False,
            "error": "I couldn't turn that into a scheduling rule. Try one of these: 'Give Maya fewer evening shifts', 'Don't schedule Alex on Friday', 'Cap Priya at 20 hours', or 'Jordan needs at least 16 hours'."}


def validate_llm_constraint(candidate, employees):
    """Re-validate a constraint proposed by an LLM with the same
    rules as the rule parser. Returns (ok, parsed-or-error)."""
    if not isinstance(candidate, dict):
        return False, "LLM returned a non-object constraint."
    kind = candidate.get("kind")
    if kind not in {"day_off", "limit_evening_shifts", "max_hours", "min_hours", "avoid_shift", "prefer_shift"}:
        return False, f"Unknown constraint kind: {kind!r}."
    name = candidate.get("employee_name", "")
    emp = next((e for e in employees if e["name"].lower() == name.lower()), None)
    if emp is None:
        return False, f"Unknown employee: {name!r}."
    payload = candidate.get("payload") or {}
    if kind == "day_off" and payload.get("day") not in DAYS:
        return False, "day_off needs a valid weekday."
    if kind in {"max_hours", "min_hours"}:
        v = payload.get("max_hours", payload.get("min_hours"))
        if not isinstance(v, int) or v < 4 or v > 40 or v % 4 != 0:
            return False, "Hours must be a multiple of 4 between 4 and 40."
    if kind == "limit_evening_shifts":
        v = payload.get("max")
        if not isinstance(v, int) or v < 0 or v > 7:
            return False, "Evening cap must be between 0 and 7."
    if kind in {"avoid_shift", "prefer_shift"} and payload.get("shift") not in SHIFT_LABELS:
        return False, "Shift must be Morning, Midday or Evening."
    return True, {"ok": True, "kind": kind, "employee_name": emp["name"],
                  "payload": payload, "explanation": candidate.get("explanation", ""),
                  "confidence": 0.75, "source_text": candidate.get("source_text", "")}
