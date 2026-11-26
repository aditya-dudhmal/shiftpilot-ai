"""API integration tests against a throwaway SQLite database."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{tmp.name}"

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_employees  # noqa: E402

Base.metadata.create_all(bind=engine)
# TestClient without a context manager does not run lifespan/startup,
# so seed explicitly here (the same call the app runs on startup).
seed_employees(SessionLocal())
client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_employees_seeded_and_crud():
    r = client.get("/api/employees")
    assert r.status_code == 200 and len(r.json()) >= 20
    created = client.post("/api/employees", json={
        "name": "Test Person", "role": "Server", "max_hours_per_week": 12,
        "availability": {"Monday": ["Morning"]}}).json()
    assert created["name"] == "Test Person"
    assert client.get(f"/api/employees/{created['id']}").status_code == 200
    assert client.put(f"/api/employees/{created['id']}",
                      json={"max_hours_per_week": 16}).json()["max_hours_per_week"] == 16
    assert client.delete(f"/api/employees/{created['id']}").status_code == 204
    assert client.get(f"/api/employees/{created['id']}").status_code == 404


def test_employee_validation_rejects_bad_role():
    assert client.post("/api/employees", json={
        "name": "Bad Role", "role": "Wizard", "max_hours_per_week": 20}).status_code == 422


def test_generate_and_schedule_and_export():
    gen = client.post("/api/schedules/generate", json={})
    assert gen.status_code == 200
    assert gen.json()["coverage"] >= 0.5
    sched = client.get("/api/schedules").json()
    assert len(sched["assignments"]) > 0
    assert "analytics" in sched and "conflicts" in sched
    csv = client.get("/api/export/csv")
    assert csv.status_code == 200 and "Alex Morgan" in csv.text or "week_start" in csv.text
    xlsx = client.get("/api/export/excel")
    assert xlsx.status_code == 200 and len(xlsx.content) > 1000


def test_assistant_parse_and_apply():
    r = client.post("/api/assistant/parse", json={"text": "Give Maya fewer evening shifts next week"})
    assert r.status_code == 200 and r.json()["ok"] is True
    bad = client.post("/api/assistant/parse", json={"text": "Give Zebra fewer evening shifts"})
    assert bad.json()["ok"] is False
    cons = client.get("/api/constraints").json()
    assert any(c["employee_name"] == "Maya Patel" for c in cons)
