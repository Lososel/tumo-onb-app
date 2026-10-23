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
    coach_name: str = ""  # active coach ("Coach"), falling back to "ex-Coach" when empty
    prev_coach_name: str = ""  # internal only ("ex-Coach")
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


class TabStats(BaseModel):
    """What one sheet tab produced during a sync — counts only, never names."""

    rows: int = 0  # non-empty rows read from the tab
    header_row: int | None = None  # 1-based row of the detected header (None: positional/none)
    columns: dict[str, str] = Field(default_factory=dict)  # field -> header text it was read from
    learners: int = 0  # name rows parsed
    inactive: int = 0  # of which inactive (red rows or a "left" status)
    red_rows: int = 0  # of which red-filled
    kept: int = 0  # learners from this tab that won de-duplication


class Snapshot(BaseModel):
    learners: list[LearnerRecord] = Field(default_factory=list)
    tabs: dict[str, TabStats] = Field(default_factory=dict)
    fetched_at: datetime
    source: str
    origin: str = ""  # source origin + tab filter; a cache from a different origin is ignored
