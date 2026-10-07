"""Public API shapes — the only data ever sent to the frontend.

There is deliberately no field for tumo_id, IIN or extra_info, so they cannot leak by accident.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class LookupRequest(BaseModel):
    query: str = Field(min_length=1, max_length=120)


class ScheduleCard(BaseModel):
    full_name: str
    schedule: str | None = None
    coach_name: str | None = None
    room: str | None = None
    default_email: str | None = None
    temp_password: str | None = None  # None unless EXPOSE_TEMP_PASSWORD is enabled
    status_code: str  # active_schedule | schedule_pending | schedule_changed | coach_changed | other
    status: str | None = None  # raw sheet text, shown when status_code == "other"


class LookupResponse(BaseModel):
    status: Literal["ok", "not_found", "inactive", "need_full_name", "too_many"]
    results: list[ScheduleCard] = Field(default_factory=list)
    data_updated_at: datetime | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "no_data"]
    source: str
    learners_cached: int
    data_updated_at: datetime | None
    last_sync_error: str | None
