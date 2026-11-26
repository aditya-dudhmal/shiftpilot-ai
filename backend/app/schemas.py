"""Pydantic schemas — the API's input validation boundary.

Every write goes through one of these, so bad data (a 200-hour week,
an unknown role, a nonsense day) is rejected with a clear 422 before
it can reach the scheduler or the database.
"""
from pydantic import BaseModel, Field, field_validator

from .config import DAYS, ROLES, SHIFTS

SHIFT_LABELS = [s[0] for s in SHIFTS]


class EmployeeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role: str
    email: str = ""
    max_hours_per_week: int = Field(20, ge=4, le=40)
    availability: dict[str, list[str]] = {}
    notes: str = ""

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        return v

    @field_validator("availability")
    @classmethod
    def _availability(cls, v: dict) -> dict:
        for day, shifts in v.items():
            if day not in DAYS:
                raise ValueError(f"unknown day: {day}")
            for s in shifts:
                if s not in SHIFT_LABELS:
                    raise ValueError(f"unknown shift: {s}")
        return v


class EmployeeUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    email: str | None = None
    max_hours_per_week: int | None = Field(None, ge=4, le=40)
    availability: dict[str, list[str]] | None = None
    notes: str | None = None


class EmployeeOut(BaseModel):
    id: int
    name: str
    role: str
    email: str
    max_hours_per_week: int
    availability: dict
    notes: str

    model_config = {"from_attributes": True}


class AssistantRequest(BaseModel):
    text: str = Field(..., min_length=3, max_length=500)
    week_start: str | None = None


class GenerateRequest(BaseModel):
    week_start: str | None = None
    # If true, wipe this week's assignments before generating.
    replace: bool = True
