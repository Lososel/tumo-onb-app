"""Data models.

The internal models (Snapshot, LearnerRecord) hold only allow-listed fields parsed from
the sheet. Anything else in the sheet, such as an IIN or phone column added by mistake,
is dropped during parsing and never cached or saved.

The public models (*Out, LookupResponse) are the only shapes ever sent to the frontend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------- Internal (cached) ----------


class LearnerRecord(BaseModel):
    tokens: list[str]  # normalized name tokens used for matching
    full_name: str
    active: bool = True
    schedule: str = ""
    schedule_kk: str = ""
    self_study_day: str = ""
    self_study_day_kk: str = ""
    coach: str = ""
    coach_email: str = ""
    stage: str = ""
    stage_code: str = ""
    status: str = ""
    status_code: str = ""
    note: str = ""
    note_kk: str = ""


class Snapshot(BaseModel):
    learners: list[LearnerRecord] = Field(default_factory=list)
    fetched_at: datetime
    source: str


# ---------- Public API ----------


class LookupRequest(BaseModel):
    query: str = Field(min_length=1, max_length=120)


class LearnerOut(BaseModel):
    full_name: str
    schedule: str | None = None
    schedule_kk: str | None = None
    self_study_day: str | None = None
    self_study_day_kk: str | None = None
    coach: str | None = None
    coach_email: str | None = None
    stage: str | None = None
    stage_code: str | None = None
    status: str | None = None
    status_code: str | None = None
    note: str | None = None
    note_kk: str | None = None


class LookupResponse(BaseModel):
    status: Literal["ok", "not_found", "inactive", "need_full_name", "too_many"]
    results: list[LearnerOut] = Field(default_factory=list)
    data_updated_at: datetime | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "no_data"]
    source: str
    learners_cached: int
    data_updated_at: datetime | None
    last_sync_error: str | None
