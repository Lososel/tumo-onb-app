"""Turns raw spreadsheet rows into a clean, whitelisted Snapshot.

Expected tabs (header row first; header matching is case/space-insensitive):

  Students:  first_name | last_name | status | self_study_days | self_study_time | workshops | whatsapp_link
  Workshops: id | name | teacher | room | days | time | whatsapp_link
  Links:     key | value          (e.g. whatsapp_default -> https://chat.whatsapp.com/...)

`workshops` on a student row is a comma-separated list of Workshop ids (or names).
`status` is "active" unless it says inactive/no/0/false/left/paused.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable

from .models import Snapshot, StudentRecord, Workshop

STUDENTS_TAB = "Students"
WORKSHOPS_TAB = "Workshops"
LINKS_TAB = "Links"
TABS = (STUDENTS_TAB, WORKSHOPS_TAB, LINKS_TAB)

RawTabs = dict[str, list[dict[str, Any]]]

# Header aliases -> canonical field. Only these fields are ever read; every other column is ignored.
_STUDENT_FIELDS = {
    "first_name": ("first_name", "firstname", "first", "name", "имя", "аты"),
    "last_name": ("last_name", "lastname", "last", "surname", "фамилия", "тегі"),
    "status": ("status", "active", "статус"),
    "self_study_days": ("self_study_days", "self_study_day", "selfstudy_days", "self_study"),
    "self_study_time": ("self_study_time", "selfstudy_time"),
    "workshops": ("workshops", "workshop", "workshop_ids", "workshop_id"),
    "whatsapp_link": ("whatsapp_link", "whatsapp", "whatsapp_group"),
}
_WORKSHOP_FIELDS = {
    "id": ("id", "workshop_id", "code"),
    "name": ("name", "workshop", "workshop_name", "title"),
    "teacher": ("teacher", "coach", "instructor"),
    "room": ("room", "location", "lab"),
    "days": ("days", "day"),
    "time": ("time", "hours"),
    "whatsapp_link": ("whatsapp_link", "whatsapp", "whatsapp_group"),
}
_LINK_FIELDS = {"key": ("key", "name"), "value": ("value", "url", "link")}

_INACTIVE = {"inactive", "no", "0", "false", "left", "paused", "archived", "неактивен"}


def _header_key(h: str) -> str:
    return re.sub(r"[\s\-]+", "_", str(h).strip().lower())


def _pick(row: dict[str, Any], fields: dict[str, tuple[str, ...]]) -> dict[str, str]:
    """Project a raw row onto the whitelisted fields, dropping all other columns."""
    normalized = {_header_key(k): v for k, v in row.items()}
    out: dict[str, str] = {}
    for canonical, aliases in fields.items():
        value = next((normalized[a] for a in aliases if a in normalized), "")
        out[canonical] = str(value).strip() if value is not None else ""
    return out


def normalize_name(name: str) -> str:
    """Normalize a person's name into an order-insensitive lookup key.

    "  Aruzhan   SMAGULOVA " == "smagulova aruzhan"; ё/е and diacritics are folded.
    """
    # NFKD splits accented letters (é, ё, й) into base + combining mark; dropping the marks
    # folds them. Both the sheet and the query go through this, so matching stays consistent.
    s = unicodedata.normalize("NFKD", name).casefold()
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    tokens = re.findall(r"\w+", s)
    return " ".join(sorted(tokens))


def _split_list(value: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,;\n]", value) if p.strip()]


def _safe_url(value: str) -> str:
    return value if value.lower().startswith(("https://", "http://")) else ""


def parse_tabs(raw: RawTabs, source: str) -> Snapshot:
    workshops: dict[str, Workshop] = {}
    by_name: dict[str, str] = {}
    for row in raw.get(WORKSHOPS_TAB, []):
        w = _pick(row, _WORKSHOP_FIELDS)
        wid = w["id"] or w["name"]
        if not wid or not w["name"]:
            continue
        workshops[wid.lower()] = Workshop(
            id=wid,
            name=w["name"],
            teacher=w["teacher"],
            room=w["room"],
            days=w["days"],
            time=w["time"],
            whatsapp_link=_safe_url(w["whatsapp_link"]),
        )
        by_name[w["name"].lower()] = wid.lower()

    students: list[StudentRecord] = []
    for row in raw.get(STUDENTS_TAB, []):
        s = _pick(row, _STUDENT_FIELDS)
        if not s["first_name"] or not s["last_name"]:
            continue
        ids = []
        for ref in _split_list(s["workshops"]):
            key = ref.lower()
            if key in workshops:
                ids.append(key)
            elif key in by_name:
                ids.append(by_name[key])
        students.append(
            StudentRecord(
                name_key=normalize_name(f"{s['first_name']} {s['last_name']}"),
                first_name=s["first_name"],
                last_name=s["last_name"],
                active=s["status"].strip().lower() not in _INACTIVE,
                self_study_days=s["self_study_days"],
                self_study_time=s["self_study_time"],
                workshop_ids=ids,
                whatsapp_link=_safe_url(s["whatsapp_link"]),
            )
        )

    links: dict[str, str] = {}
    for row in raw.get(LINKS_TAB, []):
        link = _pick(row, _LINK_FIELDS)
        if link["key"] and link["value"]:
            links[_header_key(link["key"])] = link["value"]

    return Snapshot(
        students=students,
        workshops=workshops,
        links=links,
        fetched_at=datetime.now(timezone.utc),
        source=source,
    )


def rows_to_records(values: Iterable[list[Any]]) -> list[dict[str, Any]]:
    """Convert a 2D value grid (header row first) into a list of row dicts."""
    rows = [list(r) for r in values]
    if not rows:
        return []
    header = [str(h) for h in rows[0]]
    records = []
    for r in rows[1:]:
        if not any(str(c).strip() for c in r):
            continue
        r = r + [""] * (len(header) - len(r))
        records.append({h: r[i] for i, h in enumerate(header) if h})
    return records
