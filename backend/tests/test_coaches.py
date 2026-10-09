"""Coach directory (data/coaches.json): the sheet's coach cell -> full name + work email."""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_DIR, Settings
from app.main import create_app
from app.services.coaches import CoachDirectory

COACHES_FILE = BACKEND_DIR / "data" / "coaches.json"
DIRECTORY = CoachDirectory.load(COACHES_FILE)


@pytest.mark.parametrize(
    "cell, name, email",
    [
        ("Gulnaz", "Гулназ", "bekturganova.gulnaz@tumo.center"),
        ("Nazym", "Назым", "rysbayeva.nazym@tumo.center"),
        ("Alinur", "Әлинұр", "manap.alinur@tumo.center"),
        ("Nurai", "Нурай", "nurai.ergazyeva@tumo.center"),
        ("Nuray", "Нурай", "nurai.ergazyeva@tumo.center"),  # y/i spelling
        ("Nurasyl", "Нурасыл", "nurassyl.zhananov@tumo.center"),  # ss/s spelling
        ("Rizakhmet", "Ризахмет", "rizahmet.dauletbay@tumo.center"),  # kh/h spelling
        ("Almas", "Алмас", "almas.musalimov@tumo.center"),
        ("Dariga", "Дариға", "dariga.khassen@tumo.center"),
        ("Elmira", "Эльмира", "shainurova.elmira@tumo.center"),
        ("Alen", "Ален", "zhumagali.alen@tumo.center"),
        ("Tahmina", "Тахмина", "t.kabylbek@tumo.center"),
        ("  NAZYM ", "Назым", "rysbayeva.nazym@tumo.center"),
        ("Назым", "Назым", "rysbayeva.nazym@tumo.center"),
        ("Әлинұр", "Әлинұр", "manap.alinur@tumo.center"),
        ("Алинур", "Әлинұр", "manap.alinur@tumo.center"),  # typed without Kazakh letters
        ("Dana T.", "Дана Телжан", "telzhan.dana@tumo.center"),
        ("Dana Kurak", "Дана Құрақ", "kurak.dana@tumo.center"),
        ("Құрақ Дана", "Дана Құрақ", "kurak.dana@tumo.center"),
        ("Ахметова Дана", "Дана Ахметова", "akhmetova.dana@tumo.center"),
        ("Aruzhan Kh.", "Аружан Хамзина", "khamzina.aruzhan@tumo.center"),
        ("Aruzhan T", "Аружан Төребек", "torebek.aruzhan@tumo.center"),
        ("Мырзахмет Аружан", "Аружан Мырзахмет", "aruzhan.myrzakhmet@tumo.center"),
        ("Kurak.Dana@tumo.center", "Дана Құрақ", "kurak.dana@tumo.center"),
    ],
)
def test_resolves_sheet_spellings(cell, name, email):
    assert DIRECTORY.resolve(cell) == (name, email)


@pytest.mark.parametrize("cell", ["Dana", "Aruzhan", "Дана", "Аружан"])
def test_ambiguous_first_names_get_no_email(cell):
    # Three coaches share each of these names: never guess (and show) the wrong email.
    assert DIRECTORY.find(cell) is None
    assert DIRECTORY.resolve(cell) == (cell, None)


@pytest.mark.parametrize("cell", ["", "A", "T", "Aliya", "unknown@tumo.center", "Samat"])
def test_unknown_coaches_are_shown_as_written(cell):
    assert DIRECTORY.find(cell) is None
    assert DIRECTORY.resolve(cell)[1] is None


def test_directory_matches_the_team_list_exactly():
    entries = json.loads(COACHES_FILE.read_text(encoding="utf-8"))
    assert len(DIRECTORY.coaches) == len(entries) == 29
    for coach, entry in zip(DIRECTORY.coaches, entries):
        assert coach.name == entry["name"]
        assert coach.email == entry["email"] == entry["email"].lower()
        assert DIRECTORY.find(coach.email) == coach  # every coach reachable by email


def test_missing_or_broken_file_means_no_resolution(tmp_path):
    assert CoachDirectory.load(tmp_path / "missing.json").resolve("Nazym") == ("Nazym", None)
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert CoachDirectory.load(broken).coaches == []


def test_card_shows_full_name_and_email(tmp_path):
    sheet = tmp_path / "s.json"
    sheet.write_text(json.dumps({"4 поток": [
        ["ФИО ребенка", "Расписание", "Коуч"],
        ["Сидоров Максим", "Пн/Чт 14:30-16:30", "Alinur"],
        ["Иванова Анна", "Пн/Чт 10:30-12:30", "Dana"],
        ["Петров Олег", "Вт/Пт 10:30-12:30", "Aliya"],
    ]}), encoding="utf-8")
    with TestClient(create_app(Settings(mock_file=sheet, cache_file=tmp_path / "c.json"))) as c:
        def coach(q):
            card = c.post("/api/schedule/lookup", json={"query": q}).json()["results"][0]
            return card["coach_name"], card["coach_email"]

        assert coach("сидоров максим") == ("Әлинұр", "manap.alinur@tumo.center")
        assert coach("иванова анна") == ("Dana", None)  # ambiguous: as written, no email
        assert coach("петров олег") == ("Aliya", None)  # not in the list yet


def test_patronymic_prefix_does_not_match_another_coach():
    # "Arman" is only the start of Канбакова Данель Арманқызы's patronymic, not a coach's name.
    assert DIRECTORY.find("Arman") is None


def test_display_is_first_name_with_surname_only_for_shared_first_names():
    shown = {c.email: c.display for c in DIRECTORY.coaches}
    assert shown["rysbayeva.nazym@tumo.center"] == "Назым"
    assert shown["t.kabylbek@tumo.center"] == "Тахмина"  # patronymic and surname dropped
    assert shown["dariya.aidyn@tumo.center"] == "Дария"  # first-name-first entry
    assert shown["dariga.khassen@tumo.center"] == "Дариға"  # similar but different name
    danas = sorted(v for v in shown.values() if v.startswith("Дана"))
    aruzhans = sorted(v for v in shown.values() if v.startswith("Аружан"))
    assert danas == ["Дана Ахметова", "Дана Телжан", "Дана Құрақ"]
    assert aruzhans == ["Аружан Мырзахмет", "Аружан Төребек", "Аружан Хамзина"]
    assert sum(" " in v for v in shown.values()) == 6  # only the shared first names get a surname


def test_entries_without_first_name_show_the_full_name():
    d = CoachDirectory.from_entries([{"name": "Новый Коуч", "email": "new.coach@tumo.center"}])
    assert d.resolve("new.coach@tumo.center") == ("Новый Коуч", "new.coach@tumo.center")
