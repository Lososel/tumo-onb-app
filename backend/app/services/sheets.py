"""Dynamic Google Sheet parser.

Reads every tab of the spreadsheet as a raw value grid and maps columns to our schema by
header name, so column order and exact wording can change freely:

  full_name        "ФИО", "ФИО ребенка", "ФИО ученика", "Full Name" ...   (required)
  schedule         "Расписание", "График", "Schedule"
  coach_name       "Coach", "Коуч"            (active coach)
  room             "Зона", "Кабинет", "Комната", "Room"
  default_email    "Почта TUMO", "Почта", "Email", "E-mail"
  temp_password    "Временный пароль", "Пароль", "Password"
  tumo_id          "TUMO ID", "ID"
  status           "Статус", "Status"   (optional)
  prev_coach_name  "ex-Coach"           (optional; fallback when Coach is empty)
  extra_info       every other column (kept server-side only, never sent to the public API)

Header detection: the first of the top rows that names at least two known fields is the header
(title rows above it are skipped). An exact alias beats a partial one ("Coach" beats "ex-Coach"
for coach_name); among equals the leftmost column wins. A tab with no recognizable header row
falls back to positional mapping in the order above. Tabs without names are skipped.

Privacy: columns whose header looks like an IIN, phone, birth date, address, or a parent's or
child's personal contact ("ФИО родителя", "почта ребенка", "номер ребенка") are ignored
completely — never mapped to a field, never kept in extra_info. 12-digit IIN-shaped values are
also dropped from extra_info.
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
    "room": ("room", "кабинет", "комната", "аудитория", "бөлме", "зона", "zone"),
    "default_email": (
        "email", "e mail", "mail", "почта", "электронная почта",
        "почта tumo", "tumo email", "tumo почта", "tumo mail",
    ),
    "temp_password": ("password", "temp password", "пароль", "временный пароль", "құпия сөз"),
    "tumo_id": ("tumo id", "id", "tumo айди"),
    "status": ("status", "статус"),
    "prev_coach_name": ("ex coach", "previous coach", "бывший коуч", "предыдущий коуч", "старый коуч"),
}
POSITIONAL_FIELDS = list(FIELD_ALIASES)[:7]  # status / prev coach are never assumed positionally

HEADER_SCAN_ROWS = 5  # how many top rows may hold titles before the header row
POSITIONAL_MIN_CELLS = 3  # header-less tabs: rows with fewer filled cells are notes/titles

# Column headers whose data we refuse to keep anywhere (matched as substrings of the header).
_SENSITIVE_HEADER = re.compile(
    r"иин|iin|жсн|паспорт|passport|удостоверени|телефон|phone|тел\b|мобильн|whatsapp|"
    r"номер (?:ребен|ребён|родит|телеф)|дата рождения|день рождения|\bдр\b|birth|туған|"
    r"адрес|address|мекенжай|родител|parent|"
    r"почта (?:ребен|ребён)|email (?:ребен|ребён)|child email|personal email",
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
    "waitlist": ("waitlist", "wait list", "лист ожидания", "в листе ожидания", "күту тізімі"),
    "active_schedule": ("active", "активный", "активный график", "активен"),
}
_WAITLIST_IN_SCHEDULE = re.compile(r"лист\w* ожидани|wait\s?list|күту тізім", re.IGNORECASE)


# ---------- normalization ----------


def clean_text(value: Any) -> str:
    """Trim, collapse whitespace (incl. non-breaking spaces) and drop control chars.

    Multi-line cells keep their line structure as ", ": "WR 5\\n3 этаж" -> "WR 5, 3 этаж".
    """
    s = unicodedata.normalize("NFC", str(value if value is not None else ""))
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C" or ch in "\t\n\r")
    lines = (" ".join(line.split()) for line in s.splitlines())
    return ", ".join(line for line in lines if line)


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


EXACT, PARTIAL = 2, 1  # header match quality


def _match_header_scored(header: Any) -> tuple[str, int] | None:
    """Map one header cell to (field, EXACT|PARTIAL), or None if unknown, ambiguous or sensitive.

    Sensitive headers ("ФИО родителя", "почта ребенка", "ИИН ребенка") never map to a field.
    An exact alias match wins. Otherwise an alias whose words all appear in the header counts
    ("ФИО ребенка" -> full_name), unless the header hits several fields ("Email коуча" hits
    both default_email and coach_name) — ambiguous headers are treated as extra info.
    """
    if _SENSITIVE_HEADER.search(clean_text(header)):
        return None
    h = _header_words(header)
    if not h:
        return None
    for field, aliases in FIELD_ALIASES.items():
        if h in aliases:
            return field, EXACT
    words = h.split()
    hits = {
        field
        for field, aliases in FIELD_ALIASES.items()
        if any(all(_word_in(a, words) for a in alias.split()) for alias in aliases)
    }
    return (hits.pop(), PARTIAL) if len(hits) == 1 else None


def match_header(header: Any) -> str | None:
    scored = _match_header_scored(header)
    return scored[0] if scored else None


def _word_in(alias_word: str, words: list[str]) -> bool:
    """Alias word appears in the header, tolerating Russian case endings (коуч ~ коуча, почта ~ почты)."""
    stem = alias_word[:-1] if len(alias_word) >= 5 else alias_word
    return any(w.startswith(stem) for w in words)


def detect_columns(grid: Grid) -> tuple[int, dict[str, int], dict[int, str]]:
    """Return (first_data_row, field -> column index, extra column index -> header).

    Falls back to positional mapping (first_data_row = 0) when no header row is found.
    """
    for r, row in enumerate(grid[:HEADER_SCAN_ROWS]):
        best: dict[str, tuple[int, int]] = {}  # field -> (quality, column)
        candidates: dict[int, str] = {}  # every non-sensitive, non-empty header
        for c, cell in enumerate(row):
            text = clean_text(cell)
            if not text or _SENSITIVE_HEADER.search(text):
                continue  # sensitive columns are dropped entirely, not even kept as extras
            candidates[c] = text
            scored = _match_header_scored(cell)
            if scored:
                field, quality = scored
                if field not in best or quality > best[field][0]:  # leftmost wins among equals
                    best[field] = (quality, c)
        fields = {field: c for field, (_, c) in best.items()}
        if "full_name" in fields and len(fields) >= 2:
            used = set(fields.values())
            extras = {c: h for c, h in candidates.items() if c not in used}
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
    if not schedule:
        return "schedule_pending"
    # e.g. "Понедельник, Четверг : 10:30–12:30 (лист ожидания)"
    return "waitlist" if _WAITLIST_IN_SCHEDULE.search(schedule) else "active_schedule"


def _cell(row: list[Any], idx: int | None) -> str:
    return clean_text(row[idx]) if idx is not None and idx < len(row) else ""


def parse_grid(tab: str, grid: Grid) -> list[LearnerRecord]:
    start, fields, extras = detect_columns(grid)
    if "full_name" not in fields:
        return []
    positional = start == 0
    safe_extras = extras  # detect_columns already excluded sensitive headers

    learners = []
    for row in grid[start:]:
        # Without a header we can't tell a learner from a note or title line by column name,
        # so require a row that actually looks like a record (name plus a couple of fields).
        if positional and sum(1 for c in row if clean_text(c)) < POSITIONAL_MIN_CELLS:
            continue
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
                coach_name=get("coach_name") or get("prev_coach_name"),
                prev_coach_name=get("prev_coach_name"),
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
