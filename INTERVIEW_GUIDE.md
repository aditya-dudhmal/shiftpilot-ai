# ShiftPilot AI — Interview Guide

How this app works, why it is built the way it is, and how to talk about
it, modify it, and debug it on your own. Read this before an interview,
not during one: the goal is to be able to explain every decision here
without notes.

## 1. The problem, in one paragraph

A campus dining hall (Sodexo at Minot State, in my case) rosters ~20
student workers a week in Excel. The manager juggles class schedules,
hour caps, evening-aversion, and last-minute requests ("give Alex fewer
evenings") by hand. That produces three real failures: stations go
short-staffed, someone gets scheduled over their hour cap, and the same
reliable people get loaded with evenings while part-timers sit idle.
ShiftPilot replaces the spreadsheet with an optimiser that sees the
whole week at once, a plain-English way to add constraints, and a check
that reports exactly what is still short — instead of hiding it.

## 2. How the app works (the 2-minute version)

1. **Roster in.** 20 synthetic employees with a role (Cook / Server /
   Cashier / Dishwasher / Supervisor), a weekly max-hours cap, and
   availability per day per shift. Stored in SQLite via SQLAlchemy.
2. **Requirements in.** Per shift, per role, how many people each
   station needs (e.g. Midday needs 2 cooks, 2 servers, 1 cashier,
   1 dishwasher, 1 supervisor). 126 slots/week total.
3. **Optimise.** OR-Tools CP-SAT assigns binary variables
   `x[employee, day, shift]` under hard constraints (availability,
   one shift/day, max hours, no evening-then-next-morning, and any
   validated NL constraints) and maximises coverage, then fairness.
   Result on the demo roster: 105 shifts, 83.3% coverage, fairness 83.2.
4. **Adjust in English.** "Give Alex fewer evening shifts next week"
   is parsed into a typed constraint (`limit_evening_shifts`, max 1),
   validated, saved, and applied on the next generate. No API key is
   needed: the built-in rule parser handles the common sentences.
   With a key set, an LLM may *propose* a constraint, but the same
   validation runs before anything is stored.
5. **Check.** Conflict detection reports understaffing, overtime,
   double-booking, availability violations, 6+ consecutive days and
   "clopenings" (evening → next morning). Analytics shows hours per
   employee, coverage, and a fairness score.
6. **Export.** CSV and Excel (with a per-employee hours sheet).

## 3. Architecture

```
React (Vite) ── fetch/JSON ──► FastAPI ──► SQLAlchemy ──► SQLite
  Dashboard / Schedule /        │  app/main.py (routes)
  Employees / Assistant /       │  app/scheduler.py (OR-Tools CP-SAT)
  Analytics (Recharts)          │  app/nl_parser.py (rule parser + validation)
  Dark mode, responsive         │  app/ai_assistant.py (optional LLM proposer)
                                │  app/conflicts.py (checks + analytics)
                                │  app/export_utils.py (CSV / Excel)
                                │  app/seed.py (20 synthetic employees)
```

Why this split: the frontend is purely presentational — every rule
lives in the backend, so the same API serves a future mobile client
or a CLI without re-implementing scheduling. SQLite is the right call
for a single-manager demo (zero setup, file-backed); the SQLAlchemy
layer means swapping to Postgres later is a one-line `DATABASE_URL`
change, not a rewrite. FastAPI was chosen over Flask for Pydantic
validation and auto-generated OpenAPI docs (`/docs`).

### Trade-offs, stated honestly

| Decision | Gain | Cost |
|---|---|---|
| CP-SAT (exact solver) | Whole-week optimum, fairness explicit | 10 s solve cap; infeasible constraint sets need a fallback |
| SQLite | Zero setup, fresh-install friendly | No concurrent writers; fine for one manager, not for a chain |
| Rule parser first, LLM optional | Works with no key, deterministic, testable | Narrower language coverage than a pure-LLM approach |
| 4-hour fixed shifts | Matches dining-hall reality; keeps the model small | Can't model split shifts or variable-length shifts yet |
| Monolith backend (one FastAPI app) | Easy to run, test and deploy free | Would need splitting if scheduling became a separate service |

## 4. The scheduling algorithm, in detail

**Variables.** `x[e,d,s] ∈ {0,1}` — employee `e` works day `d`, shift `s`.

**Hard constraints.**
- Availability: `x = 0` outside the employee's stated availability.
- One shift per employee per day.
- Max hours: `Σ x · 4h ≤ max_hours_per_week`.
- Staffing cap: assigned per (day, shift, role) `≤` required (never
  over-staff one station while another is short).
- No clopening: `x[e,d,Evening] + x[e,d+1,Morning] ≤ 1`.
- NL constraints: day-off, evening caps, hour caps/floors, avoid-shift
  become extra hard constraints.

**Objective** (weights are the design — say them out loud in an interview):
`maximise 100·(filled slots) − 10·(max shifts anyone works) − 20·(max−min shift spread) − (evening shifts)`.
Coverage dominates (100/slot). The spread term is what makes it fair:
penalising only the max left the solver indifferent between giving
Casey 2 shifts and Dana 7, because the max stayed 28h either way.
Penalising `max − min` pushes work to the least-loaded person. I found
this by testing: the first version scored fairness 4.8/100, which is
how I knew the objective was wrong, not the data.

**Fallback.** If CP-SAT is infeasible (contradictory constraints) or
OR-Tools is missing, a deterministic greedy pass fills slots
role-by-role, least-hours-first, and returns the unfilled list.
Infeasibility is surfaced (`solver: "greedy-fallback"`), never hidden.

**Complexity.** 20 employees × 7 days × 3 shifts = 420 binary
variables; CP-SAT solves it in under a second. The 10 s cap is a
safety bound, not a typical runtime.

## 5. How the AI assistant works

Two layers, and the order matters:

1. **Rule parser** (`nl_parser.py`) — regex + keyword matching over
   a closed vocabulary of kinds (`day_off`, `limit_evening_shifts`,
   `max_hours`, `min_hours`, `avoid_shift`, `prefer_shift`), days and
   shifts. "Give Alex fewer evening shifts" → first-name match → cap 1.
2. **Optional LLM proposer** (`ai_assistant.py`) — only when
   `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is set. The prompt asks for
   JSON only, with the closed vocabulary. Whatever it returns goes
   through `validate_llm_constraint`: unknown employee → reject,
   hours not a multiple of 4 or outside 4–40 → reject, unknown kind →
   reject. If the LLM fails or its proposal is invalid, the rule
   parser's answer is used instead; the request never fails because
   the LLM did.

**Why this design:** an LLM must never be able to invent an employee
or an impossible number and silently change next week's rota. The
validator is the trust boundary; the LLM is a convenience. This is
also the M3-relevant judgement call: knowing where the AI tool helps
(paraphrase handling) and where it quietly produces garbage
(unchecked constraints).

**"How LLMs work under the hood" (M3 asks this):** a transformer
predicts the next token from context via attention; it has no
grounding in your database, so its output is a plausible string, not
a fact. That is exactly why ShiftPilot treats LLM output as an
*untrusted proposal* and validates it against the roster before
storing it — the same reason you never `eval()` model output or let
it write SQL directly.

## 6. Twenty interview questions (with answers)

1. **Walk me through the project.** → Section 2, in order: roster →
   requirements → CP-SAT → NL constraints → conflicts → export.
2. **Why OR-Tools instead of a greedy algorithm?** → Greedy fills
   Monday first and strands Friday; it cannot see that giving Alex
   Monday morning blocks the only cook free Friday evening. CP-SAT
   searches the whole week jointly and trades coverage vs fairness
   explicitly in the objective.
3. **What does the objective function actually optimise?** →
   `100·filled − 10·max − 20·spread − evenings`. Coverage first,
   then fairness, then evening-aversion. Weights are a product
   decision, not a law of nature.
4. **How do you handle infeasible constraints?** → CP-SAT returns
   infeasible → greedy fallback fills what it can → API reports
   `solver: "greedy-fallback"` plus the exact unfilled slots.
5. **How does the NL assistant avoid hallucinating constraints?** →
   Closed vocabulary, first-name matching against the real roster,
   range checks (hours multiple of 4, 4–40; evening cap 0–7), and the
   same validator for LLM proposals as for rule parses.
6. **Why is the LLM optional?** → Cost, determinism, testability.
   Demo mode must work for a reviewer with no key. The LLM adds
   paraphrase coverage; it never adds authority.
7. **How would you scale this to 500 employees?** → CP-SAT still
   works (10k variables is fine); the bottleneck becomes the
   frontend calendar and the DB — move to Postgres, paginate the
   roster, and solve per-location with a time limit.
8. **What is CP-SAT, briefly?** → Constraint Programming with SAT
   solving: it propagates constraints to prune the search tree and
   uses SAT-style conflict learning; good for yes/no + integer
   scheduling problems with hard constraints.
9. **How do you test the scheduler?** → `test_scheduler.py` asserts
   hard constraints on generated output (availability, max hours,
   no double-booking), plus constraint-honouring tests (day-off,
   evening cap) and the empty-roster edge case.
10. **What is the fairness score, exactly?** → Coefficient of
    variation of *utilisation* (hours ÷ that person's max). A 16h
    part-timer at 16h is fully loaded, not underworked — raw hours
    would mis-score that. 100 = identical utilisation.
11. **Why FastAPI?** → Pydantic validation at the boundary (bad role
    or 200-hour week → 422 before the scheduler sees it), async-ready,
    and free OpenAPI docs at `/docs` for the reviewer.
12. **Why SQLite?** → Zero-setup demo, file-backed, and SQLAlchemy
    makes the Postgres swap a config change. Wrong for multi-writer
    production; right for this scope.
13. **How do you keep secrets out of the repo?** → `.env` is
    git-ignored, `.env.example` documents the keys without values,
    and CI never needs a key (tests run in demo mode).
14. **What did the AI coding tool get wrong while building this?** →
    My first objective penalised only the max, giving fairness 4.8;
    my first requirements asked for 140 slots from a 12-person
    roster (capacity 70). Both were caught by tests and by reading
    the output, not by trusting the generator — that is the workflow
    M3 describes: use the tool as default, keep judgement.
15. **How does the frontend handle API failure?** → `load()` catches
    fetch errors and shows a plain-language banner naming the exact
    command to start the backend, instead of a blank page.
16. **Explain the data model.** → `Employee` (role, max hours,
    availability JSON), `ShiftAssignment` (denormalised employee name
    for exports), `ScheduleConstraint` (typed, with source text and
    an active flag — constraints are deactivated, not deleted, so
    history is auditable).
17. **What would you add next?** → Shift swaps between employees,
    time-off requests with approval, per-employee cost, and a
    "what changed" diff when regenerating (so a manager can see the
    effect of one NL instruction).
18. **How do you know the app works from a fresh install?** → CI
    installs from `requirements.txt` + `npm ci` and runs tests and
    a production build on every push; I also verified it locally
    from a clean venv (see README "Verified" section).
19. **Describe a bug you fixed and how you found it.** → Coverage
    came out at −2.6: the weekly total was computed per-day (18
    slots) while unfilled slots were counted per-week (126). The
    negative number was the giveaway — a coverage metric can never
    be negative — and the fix was multiplying the denominator by 7.
20. **Why does this project matter for M3?** → It is end-to-end
    ownership of a real problem I watched happen (Excel rotas in a
    dining hall), built with an AI agent as the default workflow,
    with tests, CI, and honest reporting of what it cannot do yet —
    the exact loop in the posting: own it, ship it, demo it, improve
    it from feedback.

## 7. Walkthrough: modify, debug, explain it yourself

**Run it.**
```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000   # http://localhost:8000/docs
cd ../frontend && npm install && npm run dev  # http://localhost:5173
```

**Change one thing, then verify it.**
- *Add a role* (e.g. "Barista"): add it to `ROLES` in
  `backend/app/config.py`, add a row to `DEFAULT_REQUIREMENTS`, add
  a seed employee with that role, restart the backend, regenerate.
- *Change shift times:* edit `SHIFTS` in `config.py` — the frontend
  reads shift labels from `/api/meta`, so it follows automatically.
- *Add an NL phrase:* add a branch in `parse_instruction`
  (`nl_parser.py`), then add a test in `test_nl_parser.py` for both
  the success case and the rejection case.

**Debug it.**
- Backend won't start: read the traceback top-down; the common cause
  is a missing venv activation (`pip list | grep fastapi`).
- Schedule looks wrong: hit `GET /api/schedules` and check
  `conflicts` — it names the exact short slot. Then check
  `GET /api/constraints` for a stale active constraint.
- Tests failing: run one file verbosely —
  `python -m pytest backend/tests/test_scheduler.py -v`.
- Frontend blank: open DevTools → Network; a failed `/api/*` call
  means the backend isn't running (the UI says so in the banner).

**Explain it without notes:** cover the loop — roster, requirements,
solver, constraints, conflicts, export — then one trade-off (SQLite),
one bug you fixed (coverage −2.6 or fairness 4.8), and one limit
(no shift swaps yet). That is the whole interview story.

## 8. Résumé bullets (truthful, ready to paste)

- Built **ShiftPilot AI**, an end-to-end workforce-scheduling web app (FastAPI, React, SQLite, Google OR-Tools CP-SAT) that generates optimised weekly rosters for a 20-person dining-hall team — 83% staffing coverage with validated natural-language constraints ("give Alex fewer evening shifts") and conflict detection; 22 automated tests and GitHub Actions CI.
- Designed a validated AI-assistant layer in which an LLM may propose scheduling constraints but every proposal passes the same rule-based validation as typed input (roster, hours, and day checks), so demo mode works fully with no API key; shipped with CSV/Excel export and a dark-mode analytics dashboard.
