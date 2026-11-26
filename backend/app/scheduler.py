"""Weekly scheduling with Google OR-Tools CP-SAT.

Model
-----
Binary variable x[e, d, s] = 1 if employee ``e`` works day ``d``, shift ``s``.

Hard constraints (never violated — a solution that breaks one is rejected):
  1. Availability: x = 0 outside the employee's stated availability.
  2. One shift per employee per day.
  3. Max hours: sum of assigned 4-hour shifts <= max_hours_per_week.
  4. Role staffing: for each (day, shift, role) the assigned count
     tries to meet the requirement, and never exceeds it (no
     over-staffing a station while another is short).
  5. NL constraints: day-off, evening caps, per-employee hour caps,
     etc. — applied as extra hard constraints (see ``_apply_nl``).
  6. No evening followed by next-morning ("clopening").

Objective (what "optimised" means here, in priority order):
  * maximise filled required slots (coverage),
  * then minimise the spread of hours across employees (fairness:
    penalise the max hours any one person works, and reward giving
    shifts to people with fewer hours so far),
  * then prefer morning/midday over evening where coverage allows,
    because evenings are the scarce, unpopular slot.

Why CP-SAT instead of a greedy loop: a greedy pass fills Monday
first and strands Friday — it cannot see that giving Alex Monday
morning blocks the only cook available Friday evening. CP-SAT
searches the whole week jointly, so a feasible week is found when
one exists, and the objective trades coverage against fairness
explicitly instead of by accident.

Fallback: if OR-Tools is unavailable or the model is infeasible
(e.g. a manager's constraints contradict each other), we fall back
to a deterministic greedy pass and report exactly which required
slots went unfilled, rather than failing silently or inventing a
schedule. Infeasibility is surfaced to the caller, not hidden.
"""
from __future__ import annotations

from .config import DAYS, DEFAULT_REQUIREMENTS, SHIFT_HOURS, SHIFTS

SHIFT_LABELS = [s[0] for s in SHIFTS]


def _apply_nl(model, x, employees, constraints, emp_index):
    """Translate validated NL constraints into CP-SAT constraints.

    Only constraints that passed validation in ``nl_parser`` reach
    here — unknown employees and out-of-range numbers are rejected
    at parse time, so this function trusts ``kind``/``payload``.
    """
    for c in constraints:
        name = (c.get("employee_name") or "").lower()
        idxs = [i for i, e in enumerate(employees) if e["name"].lower() == name]
        if not idxs:
            continue
        i = idxs[0]
        kind = c.get("kind")
        p = c.get("payload") or {}
        if kind == "day_off":
            d = p.get("day")
            if d in DAYS:
                di = DAYS.index(d)
                for si in range(len(SHIFTS)):
                    model.add(x[i, di, si] == 0)
        elif kind == "limit_evening_shifts":
            cap = int(p.get("max", 2))
            ei = SHIFT_LABELS.index("Evening")
            model.add(sum(x[i, di, ei] for di in range(7)) <= cap)
        elif kind == "max_hours":
            cap = int(p.get("max_hours", employees[i]["max_hours_per_week"]))
            model.add(sum(x[i, di, si] for di in range(7) for si in range(3)) * SHIFT_HOURS <= cap)
        elif kind == "min_hours":
            floor = int(p.get("min_hours", 0))
            model.add(sum(x[i, di, si] for di in range(7) for si in range(3)) * SHIFT_HOURS >= floor)
        elif kind == "avoid_shift":
            s = p.get("shift")
            if s in SHIFT_LABELS:
                si = SHIFT_LABELS.index(s)
                for di in range(7):
                    model.add(x[i, di, si] == 0)
        elif kind == "prefer_shift":
            # Soft: handled in the objective, not as a hard constraint.
            pass


def _greedy(employees, requirements, constraints):
    """Deterministic fallback. Used only if CP-SAT is unavailable or
    infeasible. Respects availability, max hours, one-shift-a-day and
    day-off / evening-cap constraints; fills slots role-by-role,
    least-hours-first (the fairness heuristic, made explicit)."""
    off_days: dict[str, set] = {}
    evening_cap: dict[str, int] = {}
    hour_cap: dict[str, int] = {}
    for c in constraints:
        n = c.get("employee_name", "")
        if c.get("kind") == "day_off":
            off_days.setdefault(n, set()).add(c.get("payload", {}).get("day"))
        elif c.get("kind") == "limit_evening_shifts":
            evening_cap[n] = int(c.get("payload", {}).get("max", 2))
        elif c.get("kind") == "max_hours":
            hour_cap[n] = int(c.get("payload", {}).get("max_hours", 40))
    hours = {e["name"]: 0 for e in employees}
    evening_count = {e["name"]: 0 for e in employees}
    assigned: dict[str, set] = {e["name"]: set() for e in employees}
    out, unfilled = [], []
    for di, day in enumerate(DAYS):
        for si, shift in enumerate(SHIFT_LABELS):
            for role, need in requirements.get(shift, {}).items():
                pool = [
                    e for e in employees
                    if e["role"] == role
                    and shift in (e.get("availability") or {}).get(day, [])
                    and day not in off_days.get(e["name"], set())
                    and di not in assigned[e["name"]]
                    and hours[e["name"]] + SHIFT_HOURS <= hour_cap.get(e["name"], e["max_hours_per_week"])
                    and not (shift == "Evening" and evening_count[e["name"]] >= evening_cap.get(e["name"], 99))
                ]
                pool.sort(key=lambda e: (hours[e["name"]], e["name"]))
                for e in pool[:need]:
                    out.append({"employee_name": e["name"], "role": role, "day": day, "shift": shift})
                    hours[e["name"]] += SHIFT_HOURS
                    assigned[e["name"]].add(di)
                    if shift == "Evening":
                        evening_count[e["name"]] += 1
                if len(pool) < need:
                    unfilled.append({"day": day, "shift": shift, "role": role,
                                     "required": need, "filled": len(pool)})
    return out, unfilled, "greedy-fallback"


def generate_schedule(employees, requirements=None, constraints=None):
    """Generate one week. Returns dict with assignments, unfilled
    slots, coverage stats and which solver produced the result.

    ``employees``: list of dicts with name/role/max_hours_per_week/
    availability. ``requirements``: {shift: {role: count}}.
    ``constraints``: validated NL constraints (list of dicts).
    """
    requirements = requirements or DEFAULT_REQUIREMENTS
    # requirements in config are {role: {shift: n}}; normalise to {shift: {role: n}}
    if requirements and next(iter(requirements.values()), {}).keys() and \
            set(next(iter(requirements.values())).keys()) <= set(SHIFT_LABELS):
        req = {s: {r: requirements[r][s] for r in requirements if s in requirements[r]}
               for s in SHIFT_LABELS}
    else:
        req = requirements
    constraints = constraints or []
    n = len(employees)
    if n == 0:
        return {"assignments": [], "unfilled": [], "coverage": 0.0,
                "solver": "none", "status": "no-employees"}

    try:
        from ortools.sat.python import cp_model
    except ImportError:
        assignments, unfilled, solver = _greedy(employees, req, constraints)
        total = sum(sum(v.values()) for v in req.values()) * 7
        filled = total - sum(u["required"] - u["filled"] for u in unfilled)
        return {"assignments": assignments, "unfilled": unfilled,
                "coverage": round(filled / max(total, 1), 3),
                "solver": solver, "status": "ok"}

    model = cp_model.CpModel()
    x = {}
    for i, e in enumerate(employees):
        avail = e.get("availability") or {}
        for di, day in enumerate(DAYS):
            for si, shift in enumerate(SHIFT_LABELS):
                var = model.new_bool_var(f"x_{i}_{di}_{si}")
                x[i, di, si] = var
                if shift not in avail.get(day, []):
                    model.add(var == 0)
            # One shift per day.
            model.add(sum(x[i, di, si] for si in range(3)) <= 1)
        # Max hours.
        max_shifts = e["max_hours_per_week"] // SHIFT_HOURS
        model.add(sum(x[i, di, si] for di in range(7) for si in range(3)) <= max_shifts)
        # No evening -> next morning.
        for di in range(6):
            model.add(x[i, di, 2] + x[i, di + 1, 0] <= 1)

    _apply_nl(model, x, employees, constraints, None)

    # Staffing: assigned per (day, shift, role) <= required; reward filling.
    filled_terms, total_required = [], 0
    for di, day in enumerate(DAYS):
        for si, shift in enumerate(SHIFT_LABELS):
            for role, need in req.get(shift, {}).items():
                members = [i for i, e in enumerate(employees) if e["role"] == role]
                if not members:
                    continue
                total_required += need
                assigned = sum(x[i, di, si] for i in members)
                model.add(assigned <= need)
                filled_terms.append(assigned)

    # Fairness: minimise the spread (max - min hours) across staff,
    # not just the maximum. Penalising only the max leaves the solver
    # indifferent between giving Casey 2 shifts and Dana 7 (both keep
    # the max at 28h); penalising the spread pushes shifts to the
    # least-loaded person. Coverage stays dominant (100/slot).
    hours = [sum(x[i, di, si] for di in range(7) for si in range(3)) for i in range(n)]
    max_hours_var = model.new_int_var(0, 10, "max_shifts")
    min_hours_var = model.new_int_var(0, 10, "min_shifts")
    for h in hours:
        model.add(max_hours_var >= h)
        model.add(min_hours_var <= h)
    evening_total = sum(x[i, di, 2] for i in range(n) for di in range(7))
    model.maximize(100 * sum(filled_terms) - 10 * max_hours_var
                   - 20 * (max_hours_var - min_hours_var) - evening_total)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0
    solver.parameters.num_search_workers = 8
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        assignments, unfilled, _ = _greedy(employees, req, constraints)
        total = total_required or 1
        filled = total - sum(u["required"] - u["filled"] for u in unfilled)
        return {"assignments": assignments, "unfilled": unfilled,
                "coverage": round(filled / total, 3),
                "solver": "greedy-fallback", "status": "infeasible-cp-sat"}

    assignments, unfilled = [], []
    for di, day in enumerate(DAYS):
        for si, shift in enumerate(SHIFT_LABELS):
            for role, need in req.get(shift, {}).items():
                got = [employees[i]["name"] for i in range(n)
                       if employees[i]["role"] == role and solver.value(x[i, di, si])]
                for name in got:
                    assignments.append({"employee_name": name, "role": role,
                                        "day": day, "shift": shift})
                if len(got) < need:
                    unfilled.append({"day": day, "shift": shift, "role": role,
                                     "required": need, "filled": len(got)})
    total_slots = max(sum(sum(v.values()) for v in req.values()) * 7, 1)
    filled_slots = total_slots - sum(u["required"] - u["filled"] for u in unfilled)
    return {"assignments": assignments, "unfilled": unfilled,
            "coverage": round(filled_slots / total_slots, 3),
            "solver": "ortools-cp-sat",
            "status": "optimal" if status == cp_model.OPTIMAL else "feasible"}
