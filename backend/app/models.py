"""Internal (cached) data models, produced by services.sheets.

Columns that look like IINs, phone numbers, birth dates or addresses are dropped during
parsing and never reach these models. Public response shapes live in schemas/.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LearnerRecord(BaseModel):
    tokens: list[str]  # normalized name tokens used for matching
    full_name: str
    schedule: str = ""
    coach_name: str = ""
    room: str = ""
    default_email: str = ""
    temp_password: str = ""  # returned only when EXPOSE_TEMP_PASSWORD is enabled
    tumo_id: str = ""  # internal: de-duplication only, never returned
    status: str = ""
    status_code: str = ""
    extra_info: dict[str, str] = Field(default_factory=dict)  # internal only, never returned
    tab: str = ""

    @property
    def active(self) -> bool:
        return self.status_code != "inactive"


class Snapshot(BaseModel):
    learners: list[LearnerRecord] = Field(default_factory=list)
    fetched_at: datetime
    source: str
