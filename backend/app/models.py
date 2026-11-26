"""Database models.

Availability is stored as JSON: ``{"Monday": ["Morning", "Midday"], ...}``
— a day maps to the shift labels the employee can work that day.
An empty list means unavailable that day; a missing day means the
same. This keeps the schema simple and matches how a manager thinks
("Alex can't do evenings") without a separate availability table.

Constraints (from the NL assistant) are stored the same way the
scheduler reads them: a typed record with a JSON payload, so a
validated constraint can be listed, deleted, and re-applied on the
next generate without re-parsing the sentence.
"""
from sqlalchemy import Column, ForeignKey, Integer, JSON, String

from .database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # see config.ROLES
    email = Column(String, default="")
    max_hours_per_week = Column(Integer, default=20)
    availability = Column(JSON, default=dict)  # {day: [shift labels]}
    notes = Column(String, default="")


class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    employee_name = Column(String, nullable=False)  # denormalised for exports
    role = Column(String, nullable=False)
    day = Column(String, nullable=False)
    shift = Column(String, nullable=False)  # Morning | Midday | Evening
    week_start = Column(String, nullable=False)  # YYYY-MM-DD Monday


class ScheduleConstraint(Base):
    __tablename__ = "schedule_constraints"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String, nullable=False)
    # e.g. day_off, limit_evening_shifts, max_hours, min_hours,
    #      prefer_shift, avoid_shift, require_day_off
    employee_name = Column(String, nullable=False)
    payload = Column(JSON, default=dict)
    source_text = Column(String, default="")
    week_start = Column(String, nullable=False)
    active = Column(Integer, default=1)  # 1 = active, 0 = removed
