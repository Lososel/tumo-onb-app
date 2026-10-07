"""Dynamic Google Sheet parser.

Reads every tab of the spreadsheet as a raw value grid and maps columns to our schema by
header name, so column order and exact wording can change freely:

  full_name      "ФИО", "ФИО ученика", "Full Name", "Имя Фамилия" ...   (required)
  schedule       "Расписание", "График", "Schedule"
  coach_name     "Коуч", "Coach"
  room           "Кабинет", "Комната", "Room"
  default_email  "Почта", "Email", "E-mail"
  temp_password  "Пароль", "Временный пароль", "Password"
  tumo_id        "TUMO ID", "ID"
  status         "Статус", "Status"   (optional)
  extra_info     every other column (kept server-side only, never sent to the public API)

Header detection: the first of the top rows that names at least two known fields is the header
(title rows above it are skipped). A tab with no recognizable header row falls back to
positional mapping in the order above. Tabs without names (notes, pivots) are skipped.

Privacy: columns that look like national IDs, phones, birth dates or addresses are dropped
even from extra_info, as are 12-digit IIN-shaped values.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from ..models import LearnerRecord, Snapshot

# A grid is the tab's cell values, top row first. RawTabs maps tab title -> grid.
Grid = list[list[Any]]
RawTabs = dict[str, Grid]

# Order matters: it is also the positional fallback when a tab has no header row.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "full_name": ("full name", "fullname", "name", "фио", "аты жөні", "имя фамилия", "учащийся", "ученик"),
    "schedule": ("schedule", "расписание", "график", "кесте"),
    "coach_name": ("coach", "coach name", "коуч", "куратор"),
    "room": ("room", "кабинет", "комната", "аудитория", "бөлме"),
    "default_email": ("email", "e mail", "mail", "почта", "электронная почта"),
    "temp_password": ("password", "temp password", "пароль", "временный пароль", "құпия сөз"),
    "tumo_id": ("tumo id", "id", "tumo айди"),
    "status": ("status", "статус"),
}
POSITIONAL_FIELDS = list(FIELD_ALIASES)[:7]  # status is never assumed positionally

HEADER_SCAN_ROWS = 5  # how many top rows may hold titles before the header row

# Column headers whose data we refuse to keep anywhere (matched as substrings of the header).
_SENSITIVE_HEADER = re.compile(
    r"иин|iin|жсн|паспорт|passport|удостоверени|телефон|phone|тел\b|дата рождения|birth|"
    r"туған|адрес|address|мекенжай|родител|parent",
    re.IGNORECASE,
)
_IIN_VALUE = re.compile(r"^\d{12}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Kazakh-specific letters folded to their closest Russian letter, so "нуртас" matches "Нұртас".
_KK_FOLD = str.maketrans(
    {"ә": "а", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "ұ": "у", "ү": "у", "һ": "х", "і": "и"}
)

_STATUS_CODES = {
    "inactive": ("inactive", "неактивен", "неактивный", "отчислен", "архив", "left"),
    "schedule_pending": ("pending", "в обработке", "уточняется", "заявка в обработке"),
    "schedule_changed": ("schedule changed", "график изменен", "расписание изменено"),
    "coach_changed": ("coach changed", "коуч изменен", "новый коуч"),
    "active_schedule": ("active", "активный", "активный график", "активен"),
}


# ---------- normalization ----------


def clean_text(value: Any) -> str:
    """Trim, collapse internal whitespace (incl. non-breaking spaces) and drop control chars."""
    s = unicodedata.normalize("NFC", str(value if value is not None else ""))
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C" or ch in "\t\n")
    return " ".join(s.split())


def name_tokens(name: str) -> list[str]:
    """Normalize a name into comparable tokens.

    Case-insensitive; folds Kazakh letters (ө ү ұ қ ғ һ і ң ә), ё→е, й→и and Latin diacritics;
    ignores punctuation and repeated spaces. The sheet and the query both go through this.
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


def normalize_tumo_id(value: str) -> str:
    return re.sub(r"[\s\-]", "", value).casefold()


def _header_words(header: Any) -> str:
    """'  ФИО   ученика: ' -> 'фио ученика' (punctuation and underscores become spaces)."""
    s = clean_text(header).casefold().replace("ё", "е")
    return " ".join(re.sub(r"[^\w]|_", " ", s).split())


# ---------- header detection ----------


def match_header(header: Any) -> str | None:
    """Map one header cell to a schema field, or None if unknown/ambiguous.

    Exact alias match wins. Otherwise an alias whose words all appear in the header counts
    ("ФИО ученика" -> full_name), unless the header hits several fields ("Email коуча" hits
    both default_email and coach_name) — ambiguous headers are treated as extra info.
    """
    h = _header_words(header)
    if not h:
        return None
    for field, aliases in FIELD_ALIASES.items():
        if h in aliases:
            return field
    words = h.split()
    hits = {
        field
        for field, aliases in FIELD_ALIASES.items()
        if any(all(_word_in(a, words) for a in alias.split()) for alias in aliases)
    }
    return hits.pop() if len(hits) == 1 else None


def _word_in(alias_word: str, words: list[str]) -> bool:
    """Alias word appears in the header, tolerating Russian case endings (коуч ~ коуча, почта ~ почты)."""
    stem = alias_word[:-1] if len(alias_word) >= 5 else alias_word
    return any(w.startswith(stem) for w in words)


def detect_columns(grid: Grid) -> tuple[int, dict[str, int], dict[int, str]]:
    """Return (first_data_row, field -> column index, extra column index -> header).

    Falls back to positional mapping (first_data_row = 0) when no header row is found.
    """
    for r, row in enumerate(grid[:HEADER_SCAN_ROWS]):
        fields: dict[str, int] = {}
        extras: dict[int, str] = {}
        for c, cell in enumerate(row):
            field = match_header(cell)
            if field and field not in fields:
                fields[field] = c
            elif clean_text(cell):
                extras[c] = clean_text(cell)
        if "full_name" in fields and len(fields) >= 2:
            return r + 1, fields, extras
    return 0, {f: i for i, f in enumerate(POSITIONAL_FIELDS)}, {}


# ---------- row parsing ----------


def _status_code(text: str, schedule: str) -> str:
    v = _header_words(text)
    for code, labels in _STATUS_CODES.items():
        if v in labels:
            return code
    if text:
        return "other"
    return "active_schedule" if schedule else "schedule_pending"


def _cell(row: list[Any], idx: int | None) -> str:
    return clean_text(row[idx]) if idx is not None and idx < len(row) else ""


def parse_grid(tab: str, grid: Grid) -> list[LearnerRecord]:
    start, fields, extras = detect_columns(grid)
    if "full_name" not in fields:
        return []
    safe_extras = {i: h for i, h in extras.items() if not _SENSITIVE_HEADER.search(h)}

    learners = []
    for row in grid[start:]:
        get = lambda f: _cell(row, fields.get(f))  # noqa: E731
        full_name = get("full_name")
        tokens = name_tokens(full_name)
        if len(tokens) < 2:  # blank rows, section titles, single-word junk
            continue
        email = get("default_email")
        schedule = get("schedule")
        status = get("status")
        extra = {}
        for i, header in safe_extras.items():
            value = _cell(row, i)
            if value and not _IIN_VALUE.match(value.replace(" ", "")):
                extra[header] = value
        learners.append(
            LearnerRecord(
                tokens=tokens,
                full_name=full_name,
                schedule=schedule,
                coach_name=get("coach_name"),
                room=get("room"),
                default_email=email if _EMAIL.match(email) else "",
                temp_password=get("temp_password"),
                tumo_id=get("tumo_id"),
                status=status,
                status_code=_status_code(status, schedule),
                extra_info=extra,
                tab=tab,
            )
        )
    return learners


def parse_tabs(raw: RawTabs, source: str) -> Snapshot:
    """Parse every tab; the same TUMO ID appearing in several tabs is kept once (first wins)."""
    learners: list[LearnerRecord] = []
    seen_ids: set[str] = set()
    for tab, grid in raw.items():
        for rec in parse_grid(tab, grid):
            key = normalize_tumo_id(rec.tumo_id)
            if key:
                if key in seen_ids:
                    continue
                seen_ids.add(key)
            learners.append(rec)
    return Snapshot(learners=learners, fetched_at=datetime.now(timezone.utc), source=source)
