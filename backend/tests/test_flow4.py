"""The "4 поток" onboarding tab: parent columns first, no room/email/password columns yet.

Fixture folder = one CSV per tab ("4 поток", "3 поток"), fake data only.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.sheets import parse_tabs, select_tabs
from app.sources import CsvSource

EXPORT = Path(__file__).parent / "fixtures" / "sheet_export"
PERSONAL = ["Тестова", "Примерова", "87000000011", "87000000012", "87000000021", "87000000022",
            "parent.a@example.com", "parent.b@example.com", "03.03.2013", "04.04.2012"]


@pytest.mark.parametrize("tab_filter", ["4 поток", "4 ПОТОК", "  4   поток "])
def test_select_tabs_case_and_space_insensitive(tab_filter):
    titles = ["1 поток", "MAIN_ОБЩИЙ - 4 Поток", "3 поток"]
    assert select_tabs(titles, tab_filter) == ["MAIN_ОБЩИЙ - 4 Поток"]


def test_select_tabs_without_filter_or_match_uses_all():
    titles = ["1 поток", "3 поток"]
    assert select_tabs(titles, "") == titles
    assert select_tabs(titles, "4 поток") == titles  # graceful fallback, logged as a warning


def parsed(tab_filter="4 поток"):
    return parse_tabs(CsvSource(EXPORT).fetch(), source="csv", tab_filter=tab_filter)


def test_only_target_tab_is_parsed():
    names = {r.full_name for r in parsed().learners}
    assert names == {"Сидоров Максим Игоревич", "Жұмабек Әлия Серікқызы"}
    assert "Кузнецов Даниил Олегович" in {r.full_name for r in parsed(tab_filter="").learners}


def test_columns_mapped_and_names_trimmed():
    by_name = {r.full_name: r for r in parsed().learners}
    aliya = by_name["Жұмабек Әлия Серікқызы"]  # leading/trailing spaces stripped
    assert (aliya.schedule, aliya.coach_name) == ("Понедельник, Четверг : 10:30–12:30", "Nazym")
    assert (aliya.room, aliya.default_email, aliya.temp_password) == ("", "", "")  # columns absent


def test_duplicate_student_appears_once_with_merged_fields():
    maxims = [r for r in parsed().learners if r.full_name.startswith("Сидоров")]
    assert len(maxims) == 1
    # First row had no coach; the duplicate (different spacing/case) fills it in.
    assert maxims[0].coach_name == "Aliya"
    assert maxims[0].schedule == "Вторник, Пятница : 15:00–17:00"


def test_parent_and_child_personal_columns_ignored():
    dumped = parsed().model_dump_json()
    for value in PERSONAL:
        assert value not in dumped, value


def test_future_columns_are_picked_up_when_added():
    grid = [
        ["ФИО родителя", "Номер родителя", "почта родителя", "ФИО ребенка", "Номер ребенка",
         "ДР ребенка", "Расписание", "Коуч", "learning_zone", "default_email", "temp_password"],
        ["Тестова Мария", "87000000011", "p@example.com", "Сидоров Максим", "87000000012",
         "03.03.2013", "Вт, Пт 15:00", "Aliya", "WR 3\n2 этаж", "maxim.sidorov@tumo.example", "tumo0042"],
    ]
    rec = parse_tabs({"4 поток": grid}, source="test").learners[0]
    assert (rec.room, rec.default_email, rec.temp_password) == (
        "WR 3, 2 этаж", "maxim.sidorov@tumo.example", "tumo0042",
    )


@pytest.fixture
def client(tmp_path):
    def _make(**kw):
        settings = Settings(data_source="csv", csv_path=EXPORT, tab_filter="4 поток",
                            cache_file=tmp_path / "snap.json", **kw)
        return TestClient(create_app(settings))

    return _make


def lookup(c, q):
    return c.post("/api/schedule/lookup", json={"query": q}).json()


def test_api_fallbacks_for_missing_columns(client):
    with client(expose_temp_password=True) as c:
        body = lookup(c, "Әлия Жұмабек")
        assert body["status"] == "ok"
        assert body["results"] == [
            {
                "full_name": "Жұмабек Әлия Серікқызы",
                "schedule": "Понедельник, Четверг : 10:30–12:30",
                "coach_name": "Nazym",
                "room": "Уточняется",
                "default_email": "Уточняется",
                "temp_password": None,  # no password column, even with EXPOSE_TEMP_PASSWORD on
                "status_code": "active_schedule",
                "status": None,
            }
        ]


def test_api_dedup_kazakh_lookup_and_tab_restriction(client):
    with client() as c:
        assert len(lookup(c, "максим сидоров")["results"]) == 1
        assert lookup(c, "алия жумабек")["status"] == "ok"  # typed without Kazakh letters
        assert lookup(c, "кузнецов даниил")["status"] == "not_found"  # lives in "3 поток" only
        assert c.get("/api/health").json()["learners_cached"] == 2
