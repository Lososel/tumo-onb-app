"""Data models.

Internal models (Snapshot, StudentRecord, Workshop) hold only whitelisted fields parsed from
the sheet — anything else in the sheet (e.g. an IIN or phone column someone adds by mistake)
is dropped during parsing and never cached or persisted.

Public models (*Out, LookupResponse) are the only shapes ever sent to the frontend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# ---------- Internal (cached) ----------


class Workshop(BaseModel):
    id: str
    name: str
    teacher: str = ""
    room: str = ""
    days: str = ""
    time: str = ""
    whatsapp_link: str = ""


class StudentRecord(BaseModel):
    name_key: str  # normalized, order-insensitive lookup key
    first_name: str
    last_name: str
    active: bool = True
    self_study_days: str = ""
    self_study_time: str = ""
    workshop_ids: list[str] = Field(default_factory=list)
    whatsapp_link: str = ""


class Snapshot(BaseModel):
    students: list[StudentRecord] = Field(default_factory=list)
    workshops: dict[str, Workshop] = Field(default_factory=dict)
    links: dict[str, str] = Field(default_factory=dict)
    fetched_at: datetime
    source: str


# ---------- Public API ----------


class LookupRequest(BaseModel):
    first_name: str = Field(default="", max_length=60)
    last_name: str = Field(default="", max_length=60)
    full_name: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def _require_name(self) -> "LookupRequest":
        if not (self.full_name.strip() or (self.first_name.strip() and self.last_name.strip())):
            raise ValueError("Provide full_name, or both first_name and last_name.")
        return self

    def query(self) -> str:
        return self.full_name.strip() or f"{self.first_name.strip()} {self.last_name.strip()}"


class SelfStudyOut(BaseModel):
    days: str
    time: str


class WorkshopOut(BaseModel):
    name: str
    teacher: str | None = None
    room: str | None = None
    days: str
    time: str


class LinksOut(BaseModel):
    whatsapp: str | None = None


class StudentDashboardOut(BaseModel):
    first_name: str
    last_name: str
    self_study: SelfStudyOut | None = None
    workshops: list[WorkshopOut] = Field(default_factory=list)
    links: LinksOut = Field(default_factory=LinksOut)


class LookupResponse(BaseModel):
    status: Literal["ok", "not_found", "inactive"]
    message: str
    students: list[StudentDashboardOut] = Field(default_factory=list)
    data_updated_at: datetime | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "no_data"]
    source: str
    students_cached: int
    data_updated_at: datetime | None
    last_sync_error: str | None
