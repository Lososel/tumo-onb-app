"""The "Batch №N - Распределение между коучами" export layout.

The fixture mirrors the real export (24 columns, capacity rows above a header at row index 2,
parent/child personal columns 0-10, "ex-Coach" before "Coach", room in "Зона") with fake data.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.sheets import clean_text, match_header, parse_tabs
from app.sources import CsvSource

FIXTURE = Path(__file__).parent / "fixtures" / "batch_layout_sample.csv"

# Values from the fixture's personal columns that must never be stored or returned.
SENSITIVE_VALUES = [
    "Тестова", "Примерова",  # parent names
    "111111111111", "222222222222", "333333333333", "444444444444",  # IIN-shaped
    "+7 (700)", "87000000001", "87000000002",  # phones
    "parent.one@example.com", "child.one@example.com", "child.two@example.com",  # personal emails
    "01.01.2013", "02.02.2012",  # birth dates
]


@pytest.mark.parametrize(
    "header, field",
    [
        ("ФИО ребенка", "full_name"),
        ("Расписание", "schedule"),
        ("Почта TUMO", "default_email"),
        ("Временный пароль", "temp_password"),
        ("Coach ", "coach_name"),
        ("ex-Coach ", "prev_coach_name"),
        ("Зона", "room"),
    ],
)
def test_batch_headers_map_to_fields(header, field):
    assert match_header(header) == field


@pytest.mark.parametrize(
    "header",
    ["ФИО родителя ", "ИИН родителя", "почта родителя", "почта ребенка", "номер ребенка",
     "ИИН ребенка", "номер родителя", "ДР ребенка"],
)
def test_personal_columns_never_map(header):
    assert match_header(header) is None


def test_multiline_cells_are_joined():
    assert clean_text("WR 5\n3 этаж") == "WR 5, 3 этаж"
    assert clean_text("  WR 2\r\n 2 этаж  ") == "WR 2, 2 этаж"


def test_batch_csv_parsing():
    snap = parse_tabs(CsvSource(FIXTURE).fetch(), source="csv")
    by_name = {r.full_name: r for r in snap.learners}
    assert set(by_name) == {"Петров Артём Андреевич", "Әлібек Жұмабек Серікұлы"}

    artem = by_name["Петров Артём Андреевич"]
    assert artem.schedule == "Понедельник, Четверг : 10:30–12:30 (лист ожидания)"
    assert artem.coach_name == "Nazym"  # active "Coach", not "ex-Coach"
    assert artem.prev_coach_name == "Aliya"
    assert artem.room == "WR 5, 3 этаж"
    assert artem.default_email == "artem.petrov@tumo.example"  # "Почта TUMO", not "почта ребенка"
    assert artem.temp_password == "tumo0001"
    assert artem.status_code == "waitlist"
    assert artem.tab == FIXTURE.stem

    alibek = by_name["Әлібек Жұмабек Серікұлы"]
    assert alibek.coach_name == "Dana"  # "Coach" empty -> falls back to "ex-Coach"
    assert alibek.room == "WR 2, 2 этаж"
    assert alibek.status_code == "active_schedule"


def test_personal_columns_never_stored():
    dumped = parse_tabs(CsvSource(FIXTURE).fetch(), source="csv").model_dump_json()
    for value in SENSITIVE_VALUES:
        assert value not in dumped, value


@pytest.fixture
def csv_client(tmp_path):
    def _make(**kw):
        settings = Settings(data_source="csv", csv_path=FIXTURE, cache_file=tmp_path / "snap.json", **kw)
        return TestClient(create_app(settings))

    return _make


def lookup(c, query):
    return c.post("/api/schedule/lookup", json={"query": query})


@pytest.mark.parametrize("query", ["Петров Артем", "артём петров", "ПЕТРОВ АРТ"])
def test_lookup_from_batch_csv(csv_client, query):
    with csv_client() as c:
        body = lookup(c, query).json()
        assert body["status"] == "ok"
        assert body["results"] == [
            {
                "full_name": "Петров Артём Андреевич",
                "schedule": "Понедельник, Четверг : 10:30–12:30 (лист ожидания)",
                "coach_name": "Nazym",
                "room": "WR 5, 3 этаж",
                "default_email": "artem.petrov@tumo.example",
                "temp_password": None,
                "status_code": "waitlist",
                "status": None,
            }
        ]


def test_kazakh_name_lookup_from_batch_csv(csv_client):
    with csv_client() as c:
        card = lookup(c, "Жумабек Алибек").json()["results"][0]  # typed without Kazakh letters
        assert card["full_name"] == "Әлібек Жұмабек Серікұлы"
        assert card["coach_name"] == "Dana"


def test_batch_csv_password_toggle(csv_client):
    with csv_client(expose_temp_password=True) as c:
        assert lookup(c, "петров артем").json()["results"][0]["temp_password"] == "tumo0001"
    with csv_client() as c:
        assert lookup(c, "петров артем").json()["results"][0]["temp_password"] is None


def test_batch_csv_responses_and_cache_exclude_personal_data(csv_client, tmp_path):
    with csv_client(expose_temp_password=True) as c:
        raw = lookup(c, "петров артем").text + lookup(c, "жумабек алибек").text
    cache = (tmp_path / "snap.json").read_text(encoding="utf-8")
    for value in SENSITIVE_VALUES:
        assert value not in raw, value
        assert value not in cache, value
    assert "crm.example.com" not in raw  # "Фидбек" CRM links stay server-side
