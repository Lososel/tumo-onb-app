"""Turns raw spreadsheet rows into a clean, whitelisted Snapshot.

Expected tab "Learners" (header row first; header matching is case/space-insensitive):

  full_name | schedule | self_study_day | coach | coach_email | stage | status | note | active

Optional Kazakh overrides: schedule_kk | self_study_day_kk | note_kk
(without them, the frontend translates weekday names automatically).

- `status`: a status code or its Russian label, e.g. "Коуч без изменений", "График изменен",
  "Коуч изменен", "В обработке". Unknown text is shown as-is.
- `stage`: "Самообучение" / "Воркшоп" / "Проект" (or self_study / workshop / project).
- `active`: blank means active; "нет" / "no" / "0" / "false" / "inactive" hides the schedule.

Any other column (e.g. an IIN or phone column added by mistake) is ignored and never cached.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable

from .models import LearnerRecord, Snapshot

LEARNERS_TAB = "Learners"
TABS = (LEARNERS_TAB,)

RawTabs = dict[str, list[dict[str, Any]]]

# Header aliases -> canonical field. Only these fields are ever read.
_FIELDS = {
    "full_name": ("full_name", "fullname", "name", "фио", "аты_жөні", "учащийся"),
    "schedule": ("schedule", "график", "график_обучения"),
    "schedule_kk": ("schedule_kk", "график_kk", "кесте"),
    "self_study_day": ("self_study_day", "self_study", "день_самообучения", "основной_день_самообучения"),
    "self_study_day_kk": ("self_study_day_kk",),
    "coach": ("coach", "коуч"),
    "coach_email": ("coach_email", "email_коуча", "email"),
    "stage": ("stage", "этап", "этап_обучения"),
    "status": ("status", "статус"),
    "note": ("note", "комментарий", "примечание"),
    "note_kk": ("note_kk",),
    "active": ("active", "активен"),
}

_INACTIVE = {"no", "нет", "жоқ", "0", "false", "inactive", "неактивен", "archived", "left"}

# Status label (normalized) -> code. Codes are translated in the frontend.
_STATUS_CODES = {
    "coach_unchanged": ("coach_unchanged", "коуч без изменений", "коуч остался прежним"),
    "coach_changed": ("coach_changed", "коуч изменен", "коуч изменён", "новый коуч", "смена коуча"),
    "schedule_changed": ("schedule_changed", "график изменен", "график изменён", "расписание изменено"),
    "unchanged": ("unchanged", "без изменений", "график без изменений"),
    "pending": ("pending", "в обработке", "заявка в обработке", "на рассмотрении"),
}
_STAGE_CODES = {
    "self_study": ("self_study", "самообучение", "өзіндік оқу"),
    "workshop": ("workshop", "воркшоп", "workshops"),
    "project": ("project", "проект", "проекты", "project lab"),
}

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Kazakh-specific letters folded to their closest Russian letter, so "нуртас" matches "Нұртас".
_KK_FOLD = str.maketrans({"ә": "а", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "ұ": "у", "ү": "у", "һ": "х", "і": "и"})


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


def name_tokens(name: str) -> list[str]:
    """Normalize a name into comparable tokens.

    Case-insensitive; folds Kazakh letters (ұ→у, қ→к, ...), ё→е, й→и and Latin diacritics.
    Both the sheet and the query go through this, so matching stays consistent.
    """
    s = name.casefold().translate(_KK_FOLD)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.findall(r"\w+", s)


def matches(query_tokens: list[str], record_tokens: list[str]) -> bool:
    """Every query token must be a prefix of a *different* name token (any order)."""
    available = list(record_tokens)
    for q in sorted(query_tokens, key=len, reverse=True):  # longest first avoids greedy mis-pairing
        hit = next((i for i, t in enumerate(available) if t.startswith(q)), None)
        if hit is None:
            return False
        available.pop(hit)
    return True


def _code(value: str, table: dict[str, tuple[str, ...]]) -> str:
    v = " ".join(value.casefold().replace("ё", "е").split())
    for code, labels in table.items():
        if v in {label.replace("ё", "е") for label in labels}:
            return code
    return ""


def parse_tabs(raw: RawTabs, source: str) -> Snapshot:
    learners: list[LearnerRecord] = []
    for row in raw.get(LEARNERS_TAB, []):
        r = _pick(row, _FIELDS)
        tokens = name_tokens(r["full_name"])
        if len(tokens) < 2:
            continue
        email = r["coach_email"] if _EMAIL_RE.match(r["coach_email"]) else ""
        learners.append(
            LearnerRecord(
                tokens=tokens,
                full_name=" ".join(r["full_name"].split()),
                active=r["active"].strip().lower() not in _INACTIVE,
                schedule=r["schedule"],
                schedule_kk=r["schedule_kk"],
                self_study_day=r["self_study_day"],
                self_study_day_kk=r["self_study_day_kk"],
                coach=r["coach"],
                coach_email=email,
                stage=r["stage"],
                stage_code=_code(r["stage"], _STAGE_CODES),
                status=r["status"],
                status_code=_code(r["status"], _STATUS_CODES),
                note=r["note"],
                note_kk=r["note_kk"],
            )
        )
    return Snapshot(learners=learners, fetched_at=datetime.now(timezone.utc), source=source)


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
