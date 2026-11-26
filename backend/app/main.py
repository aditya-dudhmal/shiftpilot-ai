"""ShiftPilot AI — FastAPI backend.

Run:  uvicorn app.main:app --reload --port 8000   (from backend/)
Docs: http://localhost:8000/docs

Routes are grouped by resource. All state lives in SQLite; the
frontend is a separate Vite app that calls these endpoints.
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .ai_assistant import interpret
from .config import DAYS, DEFAULT_REQUIREMENTS, ROLES, SHIFTS, WEEK_START
from .conflicts import analytics, detect_conflicts
from .database import Base, SessionLocal, engine, get_db
from .export_utils import schedule_to_csv, schedule_to_excel
from .models import Employee, ScheduleConstraint, ShiftAssignment
from .scheduler import generate_schedule
from .schemas import AssistantRequest, EmployeeCreate, EmployeeOut, EmployeeUpdate, GenerateRequest
from .seed import seed_employees

Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    db = SessionLocal()
    try:
        seed_employees(db)
    finally:
        db.close()
    yield


app = FastAPI(title="ShiftPilot AI", version="1.0.0",
              description="AI-assisted workforce scheduling for campus dining.",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _emp_dict(e: Employee) -> dict:
    return {"id": e.id, "name": e.name, "role": e.role, "email": e.email,
            "max_hours_per_week": e.max_hours_per_week,
            "availability": e.availability or {}, "notes": e.notes or ""}


def _assignments(db: Session, week: str) -> list[dict]:
    rows = db.query(ShiftAssignment).filter(ShiftAssignment.week_start == week).all()
    return [{"employee_name": r.employee_name, "role": r.role, "day": r.day, "shift": r.shift} for r in rows]


def _active_constraints(db: Session, week: str) -> list[dict]:
    rows = db.query(ScheduleConstraint).filter(
        ScheduleConstraint.week_start == week, ScheduleConstraint.active == 1).all()
    return [{"kind": r.kind, "employee_name": r.employee_name, "payload": r.payload or {}} for r in rows]


@app.get("/health")
def health():
    return {"status": "ok", "service": "shiftpilot-ai"}


@app.get("/api/meta")
def meta():
    return {"days": DAYS, "shifts": [{"label": s[0], "start": s[1], "end": s[2]} for s in SHIFTS],
            "roles": ROLES, "requirements": DEFAULT_REQUIREMENTS, "week_start": WEEK_START}


# --- Employees -------------------------------------------------------
@app.get("/api/employees", response_model=list[EmployeeOut])
def list_employees(db: Session = Depends(get_db)):
    return db.query(Employee).order_by(Employee.name).all()


@app.post("/api/employees", response_model=EmployeeOut, status_code=201)
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db)):
    e = Employee(**payload.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@app.get("/api/employees/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    e = db.get(Employee, employee_id)
    if not e:
        raise HTTPException(404, "Employee not found")
    return e


@app.put("/api/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(employee_id: int, payload: EmployeeUpdate, db: Session = Depends(get_db)):
    e = db.get(Employee, employee_id)
    if not e:
        raise HTTPException(404, "Employee not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    db.commit()
    db.refresh(e)
    return e


@app.delete("/api/employees/{employee_id}", status_code=204)
def delete_employee(employee_id: int, db: Session = Depends(get_db)):
    e = db.get(Employee, employee_id)
    if not e:
        raise HTTPException(404, "Employee not found")
    db.delete(e)
    db.commit()
    return None


# --- Scheduling ------------------------------------------------------
@app.post("/api/schedules/generate")
def generate(req: GenerateRequest, db: Session = Depends(get_db)):
    week = req.week_start or WEEK_START
    employees = [_emp_dict(e) for e in db.query(Employee).all()]
    result = generate_schedule(employees, DEFAULT_REQUIREMENTS, _active_constraints(db, week))
    if req.replace:
        db.query(ShiftAssignment).filter(ShiftAssignment.week_start == week).delete()
    for a in result["assignments"]:
        db.add(ShiftAssignment(employee_name=a["employee_name"], role=a["role"],
                               day=a["day"], shift=a["shift"], week_start=week,
                               employee_id=next((e.id for e in db.query(Employee).all()
                                                 if e.name == a["employee_name"]), 0)))
    db.commit()
    result["week_start"] = week
    result["conflicts"] = detect_conflicts(employees, result["assignments"])
    return result


@app.get("/api/schedules")
def get_schedule(week_start: str | None = None, db: Session = Depends(get_db)):
    week = week_start or WEEK_START
    employees = [_emp_dict(e) for e in db.query(Employee).all()]
    assignments = _assignments(db, week)
    return {"week_start": week, "assignments": assignments,
            "conflicts": detect_conflicts(employees, assignments),
            "analytics": analytics(employees, assignments)}


@app.get("/api/analytics")
def get_analytics(week_start: str | None = None, db: Session = Depends(get_db)):
    week = week_start or WEEK_START
    employees = [_emp_dict(e) for e in db.query(Employee).all()]
    return analytics(employees, _assignments(db, week))


@app.get("/api/conflicts")
def get_conflicts(week_start: str | None = None, db: Session = Depends(get_db)):
    week = week_start or WEEK_START
    employees = [_emp_dict(e) for e in db.query(Employee).all()]
    return {"week_start": week, "conflicts": detect_conflicts(employees, _assignments(db, week))}


# --- NL assistant / constraints --------------------------------------
@app.post("/api/assistant/parse")
def assistant_parse(req: AssistantRequest, db: Session = Depends(get_db)):
    week = req.week_start or WEEK_START
    employees = [_emp_dict(e) for e in db.query(Employee).all()]
    parsed, engine = interpret(req.text, employees, week)
    if not parsed.get("ok"):
        return {"ok": False, "error": parsed.get("error"), "engine": engine}
    db.add(ScheduleConstraint(kind=parsed["kind"], employee_name=parsed["employee_name"],
                              payload=parsed["payload"], source_text=req.text, week_start=week))
    db.commit()
    return {**parsed, "engine": engine, "saved": True,
            "note": "Saved — regenerate the schedule to apply it."}


@app.get("/api/constraints")
def list_constraints(week_start: str | None = None, db: Session = Depends(get_db)):
    week = week_start or WEEK_START
    rows = db.query(ScheduleConstraint).filter(
        ScheduleConstraint.week_start == week, ScheduleConstraint.active == 1).all()
    return [{"id": r.id, "kind": r.kind, "employee_name": r.employee_name,
             "payload": r.payload, "source_text": r.source_text} for r in rows]


@app.delete("/api/constraints/{constraint_id}", status_code=204)
def delete_constraint(constraint_id: int, db: Session = Depends(get_db)):
    r = db.get(ScheduleConstraint, constraint_id)
    if not r:
        raise HTTPException(404, "Constraint not found")
    r.active = 0
    db.commit()
    return None


# --- Export / demo ----------------------------------------------------
@app.get("/api/export/csv")
def export_csv(week_start: str | None = None, db: Session = Depends(get_db)):
    week = week_start or WEEK_START
    return Response(schedule_to_csv(_assignments(db, week), week),
                    media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=shiftpilot-{week}.csv"})


@app.get("/api/export/excel")
def export_excel(week_start: str | None = None, db: Session = Depends(get_db)):
    week = week_start or WEEK_START
    return Response(schedule_to_excel(_assignments(db, week), week),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=shiftpilot-{week}.xlsx"})


@app.post("/api/demo/reset")
def demo_reset(db: Session = Depends(get_db)):
    """Restore the synthetic demo roster and clear the week's schedule."""
    db.query(ShiftAssignment).delete()
    db.query(ScheduleConstraint).delete()
    db.query(Employee).delete()
    db.commit()
    n = seed_employees(db)
    return {"reset": True, "employees_seeded": n}


# --- Serve the built frontend (single-service deploy) ----------------
# On Render the build step copies frontend/dist into backend/static.
# API routes above take precedence (they are registered first), so
# /api/* still hits FastAPI and everything else serves the React app.
# Locally this directory usually does not exist, and the Vite dev
# server serves the frontend instead — nothing changes there.
import os as _os  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

_STATIC_DIR = _os.path.join(_os.path.dirname(__file__), "..", "static")
if _os.path.isfile(_os.path.join(_STATIC_DIR, "index.html")):
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="frontend")
