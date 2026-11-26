"""Conflict detection — pure functions over assignments.

Checks, each returned as {type, severity, message, ...}:
  * understaffed — a (day, shift, role) below its requirement.
  * overtime — an employee above max_hours_per_week.
  * double_booked — same employee, same day, two shifts.
  * consecutive_days — 6+ days in a row without a day off.
  * clopening — evening shift followed by next-morning shift.
  * unavailable — assigned outside stated availability (should not
    happen from the solver; catches manual/legacy data).
Severity: error for anything that breaks a hard rule, warning for
fatigue risks (consecutive days, clopening).
"""
from __future__ import annotations

from collections import defaultdict

from .config import DAYS, DEFAULT_REQUIREMENTS, SHIFT_HOURS, SHIFTS

SHIFT_LABELS = [s[0] for s in SHIFTS]


def detect_conflicts(employees, assignments, requirements=None):
    requirements = requirements or DEFAULT_REQUIREMENTS
    req = {s: {r: requirements[r][s] for r in requirements if s in requirements[r]}
           for s in SHIFT_LABELS}
    by_emp = defaultdict(list)
    by_slot = defaultdict(list)
    emp_by_name = {e["name"]: e for e in employees}
    conflicts = []

    for a in assignments:
        by_emp[a["employee_name"]].append(a)
        by_slot[(a["day"], a["shift"], a["role"])].append(a)

    # Understaffing.
    for day in DAYS:
        for shift in SHIFT_LABELS:
            for role, need in req.get(shift, {}).items():
                got = len(by_slot.get((day, shift, role), []))
                if got < need:
                    conflicts.append({"type": "understaffed", "severity": "error",
                                      "day": day, "shift": shift, "role": role,
                                      "required": need, "filled": got,
                                      "message": f"{day} {shift}: {role} is short — {got}/{need} staffed."})

    for name, shifts in by_emp.items():
        emp = emp_by_name.get(name)
        hours = len(shifts) * SHIFT_HOURS
        if emp and hours > emp["max_hours_per_week"]:
            conflicts.append({"type": "overtime", "severity": "error", "employee": name,
                              "hours": hours, "max_hours": emp["max_hours_per_week"],
                              "message": f"{name} is scheduled {hours}h, over their {emp['max_hours_per_week']}h weekly max."})
        # Double-booked: same day twice.
        days = defaultdict(list)
        for s in shifts:
            days[s["day"]].append(s["shift"])
        for day, ss in days.items():
            if len(ss) > 1:
                conflicts.append({"type": "double_booked", "severity": "error",
                                  "employee": name, "day": day,
                                  "message": f"{name} has two shifts on {day} ({', '.join(ss)})."})
        # Availability violations.
        if emp:
            avail = emp.get("availability") or {}
            for s in shifts:
                if s["shift"] not in avail.get(s["day"], []):
                    conflicts.append({"type": "unavailable", "severity": "error",
                                      "employee": name, "day": s["day"], "shift": s["shift"],
                                      "message": f"{name} is scheduled {s['day']} {s['shift']} but is unavailable then."})
        # Consecutive days (6+).
        worked = {DAYS.index(s["day"]) for s in shifts}
        run, longest = 0, 0
        for i in range(7):
            run = run + 1 if i in worked else 0
            longest = max(longest, run)
        if longest >= 6:
            conflicts.append({"type": "consecutive_days", "severity": "warning",
                              "employee": name, "days": longest,
                              "message": f"{name} works {longest} days in a row — consider a day off."})
        # Clopening.
        for i in range(6):
            if DAYS[i] in days and DAYS[i + 1] in days:
                if "Evening" in days[DAYS[i]] and "Morning" in days[DAYS[i + 1]]:
                    conflicts.append({"type": "clopening", "severity": "warning",
                                      "employee": name, "day": DAYS[i],
                                      "message": f"{name} closes {DAYS[i]} evening and opens {DAYS[i+1]} morning."})
    return conflicts


def analytics(employees, assignments, requirements=None):
    """Hours per employee, coverage, fairness (spread of hours)."""
    requirements = requirements or DEFAULT_REQUIREMENTS
    total_required = sum(sum(v.values()) for v in requirements.values()) * 7
    hours = {e["name"]: 0 for e in employees}
    by_role: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    for a in assignments:
        hours[a["employee_name"]] = hours.get(a["employee_name"], 0) + SHIFT_HOURS
        by_role[a["role"]] += SHIFT_HOURS
        by_day[a["day"]] += 1
    values = list(hours.values())
    mean = sum(values) / max(len(values), 1)
    # Fairness score from utilisation (hours / that person's max),
    # not raw hours: a 16h part-timer working 16h is fully loaded,
    # not underworked. 100 = everyone at the same utilisation.
    # Coefficient of variation of utilisation, capped at 1.
    utils = []
    for e in employees:
        cap = e["max_hours_per_week"] or 1
        utils.append(hours.get(e["name"], 0) / cap)
    if utils:
        u_mean = sum(utils) / len(utils)
        u_var = sum((u - u_mean) ** 2 for u in utils) / len(utils)
        fairness = round(100 * (1 - min(1.0, (u_var ** 0.5) / max(u_mean, 0.01))), 1) if u_mean else 100.0
    else:
        fairness = 100.0
    fairness = max(0, min(100, fairness))
    return {
        "total_hours": sum(values),
        "total_shifts": len(assignments),
        "coverage_pct": round(100 * len(assignments) / max(total_required, 1), 1),
        "required_slots": total_required,
        "filled_slots": len(assignments),
        "hours_per_employee": [{"name": n, "role": next((e["role"] for e in employees if e["name"] == n), ""),
                                "hours": h, "max_hours": next((e["max_hours_per_week"] for e in employees if e["name"] == n), 0)}
                               for n, h in sorted(hours.items(), key=lambda kv: -kv[1])],
        "hours_by_role": dict(by_role),
        "shifts_by_day": {d: by_day.get(d, 0) for d in DAYS},
        "fairness_score": fairness,
        "mean_hours": round(mean, 1),
        "max_hours": max(values) if values else 0,
        "min_hours": min(values) if values else 0,
    }
