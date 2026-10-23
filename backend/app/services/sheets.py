"""Dynamic Google Sheet parser.

Reads every tab of the spreadsheet as a raw value grid and maps columns to our schema by
header name, so column order and exact wording can change freely:

  full_name        "ФИО", "ФИО ребенка", "ФИО ученика", "Full Name" ...   (required)
  schedule         "Расписание", "График", "Schedule"
  coach_name       "Coach", "Коуч"            (active coach)
  room             "Зона", "learning_zone", "Кабинет", "Комната", "Room"
  default_email    "Почта TUMO", "default_email", "Почта", "Email", "E-mail"
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

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from ..models import LearnerRecord, Snapshot

log = logging.getLogger(__name__)


# ---------- Google credentials ----------


class SheetsConfigError(Exception):
    """Google Sheets is misconfigured (missing sheet id, unreadable/invalid credentials).

    Raised during a sync, never at startup, so the app keeps serving its cache. Messages
    describe what is wrong but never include credential contents.
    """


_SERVICE_ACCOUNT_FIELDS = ("type", "client_email", "private_key", "token_uri")


def parse_credentials_json(raw: str) -> dict:
    """Parse a service-account key pasted into an env var (GOOGLE_CREDENTIALS_JSON).

    Tolerates the usual copy/paste damage: real newlines inside the private key
    (strict=False), JSON wrapped in an extra layer of quotes, and a private key whose
    newlines arrived as literal backslash-n sequences.
    """
    text = (raw or "").strip()
    if not text:
        raise SheetsConfigError("GOOGLE_CREDENTIALS_JSON is empty")
    try:
        info = json.loads(text, strict=False)
        if isinstance(info, str):  # JSON pasted as a quoted string: '"{\"type\": ...}"'
            info = json.loads(info, strict=False)
    except json.JSONDecodeError as exc:
        raise SheetsConfigError(
            f"GOOGLE_CREDENTIALS_JSON is not valid JSON (line {exc.lineno}, column {exc.colno})"
        ) from None
    if not isinstance(info, dict):
        raise SheetsConfigError("GOOGLE_CREDENTIALS_JSON must be a JSON object")
    missing = [f for f in _SERVICE_ACCOUNT_FIELDS if not info.get(f)]
    if missing or info.get("type") != "service_account":
        raise SheetsConfigError(
            "GOOGLE_CREDENTIALS_JSON is not a service-account key (missing: "
            + (", ".join(missing) or "type=service_account")
            + ")"
        )
    key = str(info["private_key"])
    if "\\n" in key:
        key = key.replace("\\r\\n", "\n").replace("\\n", "\n")
    info["private_key"] = key.replace("\r\n", "\n")
    return info


def load_credentials_file(path) -> dict:
    """Read and validate a service-account key file (GOOGLE_CREDENTIALS_FILE)."""
    try:
        raw = open(path, encoding="utf-8-sig").read()
    except FileNotFoundError:
        raise SheetsConfigError(f"credentials file not found: {path}") from None
    except OSError as exc:
        raise SheetsConfigError(f"credentials file unreadable: {path} ({type(exc).__name__})") from None
    try:
        return parse_credentials_json(raw)
    except SheetsConfigError as exc:
        message = str(exc).replace("GOOGLE_CREDENTIALS_JSON", f"credentials file {path}")
        raise SheetsConfigError(message) from None

# ---------- .xlsx files stored in Google Drive ----------


def _xlsx_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))  # 1748.0 -> "1748" (numeric passwords, room numbers)
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M" if (value.hour or value.minute) else "%d.%m.%Y")
    return str(value)


def xlsx_to_tabs(data: bytes, tab_filter: str = "") -> RawTabs:
    """Read an .xlsx workbook into {tab title: grid}, applying TAB_FILTER before reading rows.

    Uses the cached cell values (what you see in the sheet), not formulas.
    """
    from io import BytesIO

    from openpyxl import load_workbook  # lazy: only needed for Drive .xlsx sources

    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise SheetsConfigError(f"file is not a readable .xlsx workbook ({type(exc).__name__})") from None
    try:
        return {title: _xlsx_grid(wb[title]) for title in select_tabs(wb.sheetnames, tab_filter)}
    finally:
        wb.close()


# A gap this long means the data has ended; what follows is formatting or stray notes.
MAX_BLANK_ROWS = 1000


class XlsxRow(list):
    """A row of cell values that also remembers which columns have a red fill."""

    red: frozenset[int] = frozenset()


def _is_red(fill: Any) -> bool:
    """Solid red or light-red fill ("FF0000", "EA9999", "F4CCCC", Excel's "FFC7CE"); not orange,
    pink, peach or yellow."""
    if fill is None or getattr(fill, "fill_type", None) != "solid":
        return False
    rgb = getattr(getattr(fill, "fgColor", None), "rgb", None)
    if not isinstance(rgb, str) or not re.fullmatch(r"[0-9A-Fa-f]{6,8}", rgb):
        return False  # theme/indexed colours: can't tell, so not red
    r, g, b = (int(rgb[-6:][i : i + 2], 16) for i in (0, 2, 4))
    return r >= 0xC8 and r - max(g, b) >= 0x20 and abs(g - b) <= 0x20


def _xlsx_grid(ws: Any) -> Grid:
    """Cell values of one tab, without the empty padding a formatted sheet can carry.

    A sheet whose formatting covers whole rows/columns declares a huge dimension (up to
    A1:XFD1048576), and read-only openpyxl pads every row to it: 16,384 cells per row, enough to
    exhaust a small server's memory. So the declared size is ignored, trailing empty cells are
    trimmed, empty rows are skipped (header detection doesn't need them) and reading stops after
    MAX_BLANK_ROWS empty rows in a row.

    Rows come back as XlsxRow, carrying which columns are filled red: staff highlight learners who
    left in red, and parse_grid marks those rows inactive.
    """
    if hasattr(ws, "reset_dimensions"):
        ws.reset_dimensions()
    grid: Grid = []
    blank = 0
    for row in ws.iter_rows():
        cells = XlsxRow(_xlsx_cell(getattr(c, "value", c)) for c in row)
        while cells and not cells[-1].strip():
            cells.pop()
        if not cells:
            blank += 1
            if blank >= MAX_BLANK_ROWS:
                break
            continue
        blank = 0
        cells.red = frozenset(
            i for i, c in enumerate(row) if i < len(cells) and _is_red(getattr(c, "fill", None))
        )
        grid.append(cells)
    return grid


def _row_is_red(row: Any, name_idx: int | None) -> bool:
    """Red when the name cell is red, or at least half of the row's filled cells are."""
    red = getattr(row, "red", None)
    if not red:
        return False
    if name_idx in red:
        return True
    filled = [i for i, c in enumerate(row) if clean_text(c)]
    return bool(filled) and 2 * sum(1 for i in filled if i in red) >= len(filled)


# A grid is the tab's cell values, top row first. RawTabs maps tab title -> grid.
Grid = list[list[Any]]
RawTabs = dict[str, Grid]

# Order matters: it is also the positional fallback when a tab has no header row.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "full_name": ("full name", "fullname", "name", "фио", "аты жөні", "имя фамилия", "учащийся", "ученик"),
    "schedule": (
        "schedule", "расписание", "график", "кесте", "дни и время", "день и время", "days and time",
        "күні мен уақыты",
    ),
    "coach_name": ("coach", "coach name", "коуч", "куратор"),
    "room": (
        "room", "кабинет", "комната", "аудитория", "бөлме", "зона", "zone", "learning zone",
        "локация", "location",
    ),
    "default_email": (
        "email", "e mail", "mail", "почта", "электронная почта", "default email",
        "почта tumo", "tumo email", "tumo почта", "tumo mail",
    ),
    "temp_password": ("password", "temp password", "пароль", "временный пароль", "құпия сөз"),
    "tumo_id": ("tumo id", "id", "tumo айди"),
    "status": ("status", "статус"),
    "prev_coach_name": ("ex coach", "previous coach", "бывший коуч", "предыдущий коуч", "старый коуч"),
    # Some tabs split the schedule into two columns; they are joined when there is no "Расписание".
    "days": ("дни", "дни занятий", "дни недели", "days", "күндері", "сабақ күндері"),
    "time": ("время", "время занятий", "time", "уақыт", "уақыты", "сабақ уақыты"),
}
POSITIONAL_FIELDS = list(FIELD_ALIASES)[:7]  # status / prev coach are never assumed positionally

HEADER_SCAN_ROWS = 15  # how many top rows may hold titles/notes before the header row
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
_NOT_LESSON_TIME = re.compile(r"отметк|timestamp|дата|date|создан|submitted")
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


# Latin letters that look like (folded) Cyrillic ones; typed Kazakh names often mix them in,
# e.g. Latin "i" for "і" or "o" in "Тoребек". Only applied inside words that contain Cyrillic.
_LATIN_LOOKALIKES = str.maketrans("aceopxyikmthb", "асеорхуикмтнв")
# Zero-width spaces/joiners, soft hyphens and BOMs pasted into cells would split a word in two.
_INVISIBLE = re.compile("[\u00ad\u200b-\u200f\u2060\ufeff]")


def name_tokens(name: str) -> list[str]:
    """Normalize a name into comparable tokens.

    Case-insensitive; folds Kazakh letters (ө ү ұ қ ғ һ і ң ә), ё→е, й→и, Latin diacritics and
    Latin look-alike letters inside Cyrillic words; ignores punctuation and repeated spaces.
    The sheet and the query both go through this.
    """
    s = _INVISIBLE.sub("", name).casefold().translate(_KK_FOLD)  # "Тұрды\u200bқұл" is one word
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return [
        t.translate(_LATIN_LOOKALIKES) if re.search("[а-я]", t) and re.search("[a-z]", t) else t
        for t in re.findall(r"\w+", s)
    ]


def _one_edit(a: str, b: str) -> bool:
    """True when a and b differ by at most one inserted, deleted, replaced or swapped letter."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    if len(a) == len(b):
        return a[i + 1 :] == b[i + 1 :] or (a[i + 2 :] == b[i + 2 :] and a[i : i + 2] == b[i : i + 2][::-1])
    return a[i:] == b[i + 1 :] if len(a) < len(b) else a[i + 1 :] == b[i:]


TYPO_MIN_LEN = 5  # shorter words must be typed exactly: one letter off would match too much


def _token_hit(q: str, t: str, typos: bool) -> bool:
    if t.startswith(q):
        return True
    # "гарифула" vs "гарифулла": compare with the record word's start of about the same length.
    return typos and len(q) >= TYPO_MIN_LEN and any(_one_edit(q, t[: len(q) + d]) for d in (-1, 0, 1))


def match_count(query_tokens: list[str], record_tokens: list[str], typos: bool = False) -> int:
    """How many query tokens are a prefix of a *different* name token (any order)."""
    available = list(record_tokens)
    count = 0
    for q in sorted(query_tokens, key=len, reverse=True):  # longest first avoids greedy mis-pairing
        hit = next((i for i, t in enumerate(available) if _token_hit(q, t, typos)), None)
        if hit is not None:
            available.pop(hit)
            count += 1
    return count


def matches(query_tokens: list[str], record_tokens: list[str]) -> bool:
    """Every query token must be a prefix of a *different* name token (any order)."""
    return match_count(query_tokens, record_tokens) == len(query_tokens)


def find_learners(query_tokens: list[str], learners: list[LearnerRecord]) -> list[LearnerRecord]:
    """Best matches for a name query, from strictest to most forgiving:

    1. exact prefixes ("Турдыкул Гарифулла" or "Тур Гар" finds "Тұрдықұл Ғарифулла Рахманқұлұлы");
    2. the same, allowing one typo in words of 5+ letters ("Гарифула").

    Two-word queries need both words; with three or more words, any two are enough, so a
    patronymic the sheet lacks or spells differently doesn't hide the student. Within a step,
    only the records matching the most words are returned.
    """
    if not query_tokens:
        return []
    need = len(query_tokens) if len(query_tokens) <= 2 else 2
    for typos in (False, True):
        scored = [(match_count(query_tokens, r.tokens, typos), r) for r in learners]
        scored = [(n, r) for n, r in scored if n >= need]
        if scored:
            best = max(n for n, _ in scored)
            return [r for n, r in scored if n == best]
    return []


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
    if "schedule" in hits:  # "Дни и время занятий" is one schedule column, not days or time
        hits -= {"days", "time"}
    if hits == {"time"} and _NOT_LESSON_TIME.search(h):  # Google Forms' "Отметка времени"
        return None
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


def is_waitlist_tab(title: str) -> bool:
    """Tabs like "4 поток (лист ожидания)" hold waitlisted learners."""
    return bool(_WAITLIST_IN_SCHEDULE.search(title))


def _status_code(text: str, schedule: str, waitlist_tab: bool = False) -> str:
    v = _header_words(text)
    for code, labels in _STATUS_CODES.items():
        if v in labels:
            return code
    if text:
        return "other"
    if waitlist_tab:
        return "waitlist"
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
    waitlist_tab = is_waitlist_tab(tab)
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
        schedule = get("schedule") or " ".join(p for p in (get("days"), get("time")) if p)
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
                status_code=(
                    "inactive" if _row_is_red(row, fields.get("full_name"))
                    else _status_code(status, schedule, waitlist_tab)
                ),
                extra_info=extra,
                tab=tab,
            )
        )
    return learners


def _tab_key(title: str) -> str:
    return " ".join(title.casefold().replace("ё", "е").split())


def select_tabs(titles: list[str], tab_filter: str) -> list[str]:
    """Tabs whose title contains `tab_filter` (case/space-insensitive, e.g. "4 поток").

    No filter -> all tabs. A filter that matches nothing also falls back to all tabs (with a
    warning), so a renamed tab degrades to "search everything" instead of an empty site.
    """
    wanted = _tab_key(tab_filter)
    if not wanted:
        return list(titles)
    picked = [t for t in titles if wanted in _tab_key(t)]
    if not picked:
        log.warning("No tab matches TAB_FILTER=%r; searching all %d tabs", tab_filter, len(titles))
        return list(titles)
    return picked


# Fields a later duplicate row may fill in when the first row left them empty.
_MERGEABLE = (
    "schedule", "coach_name", "prev_coach_name", "room", "default_email", "temp_password", "tumo_id",
)


_BATCH = re.compile(r"(\d+)\s*(?:поток|ағын|batch|flow)", re.IGNORECASE)


def batch_number(tab: str) -> int:
    """'5 поток' -> 5, 'MAIN - 4 Поток (лист ожидания)' -> 4; 0 when the title has none."""
    m = _BATCH.search(tab)
    return int(m.group(1)) if m else 0


def _tab_priority(tabs: list[str]) -> list[str]:
    """Order in which duplicates are resolved: main tabs before waitlist tabs, and within each the
    newest batch first ("5 поток" before "4 поток"); otherwise the workbook's order."""
    return sorted(tabs, key=lambda t: (is_waitlist_tab(t), -batch_number(t)))


def parse_tabs(raw: RawTabs, source: str, tab_filter: str = "") -> Snapshot:
    """Parse the selected tabs into one learner list, each student exactly once.

    Duplicates are recognised by TUMO ID or, failing that, by normalized full name (order,
    case, spacing and Kazakh letters ignored). The row from the highest-priority tab wins (see
    _tab_priority), except that an active row always beats an inactive (e.g. red) one; empty
    fields on the winner are filled from the other rows.
    """
    learners: list[LearnerRecord] = []
    by_id: dict[str, LearnerRecord] = {}
    by_name: dict[str, LearnerRecord] = {}
    tabs = _tab_priority(select_tabs(list(raw), tab_filter))
    for tab in tabs:
        for rec in parse_grid(tab, raw[tab]):
            id_key = normalize_tumo_id(rec.tumo_id)
            name_key = " ".join(sorted(rec.tokens))
            first = (by_id.get(id_key) if id_key else None) or by_name.get(name_key)
            if first is not None and not first.active and rec.active:
                # e.g. red (left) in "4 поток" but enrolled in "5 поток": the active row wins.
                first_copy = first.model_copy()
                for f in LearnerRecord.model_fields:
                    setattr(first, f, getattr(rec, f))
                rec = first_copy  # the old row only fills gaps below
            if first is not None:
                for f in _MERGEABLE:
                    if not getattr(first, f) and getattr(rec, f):
                        setattr(first, f, getattr(rec, f))
                if first.status_code == "schedule_pending" and first.schedule:
                    first.status_code = _status_code(first.status, first.schedule, is_waitlist_tab(first.tab))
                if id_key:
                    by_id.setdefault(id_key, first)
                continue
            learners.append(rec)
            by_name[name_key] = rec
            if id_key:
                by_id[id_key] = rec
    return Snapshot(learners=learners, fetched_at=datetime.now(timezone.utc), source=source)
