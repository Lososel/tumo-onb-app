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
        ("Gulnaz", "Бектурганова Гулназ", "bekturganova.gulnaz@tumo.center"),
        ("Nazym", "Рысбаева Назым", "rysbayeva.nazym@tumo.center"),
        ("Alinur", "Манап Әлинұр", "manap.alinur@tumo.center"),
        ("Nurai", "Ергазиева Нурай", "nurai.ergazyeva@tumo.center"),
        ("Nuray", "Ергазиева Нурай", "nurai.ergazyeva@tumo.center"),  # y/i spelling
        ("Nurasyl", "Жананов Нурасыл", "nurassyl.zhananov@tumo.center"),  # ss/s spelling
        ("Rizakhmet", "Даулетбай Ризахмет", "rizahmet.dauletbay@tumo.center"),  # kh/h spelling
        ("Almas", "Мусалимов Алмас", "almas.musalimov@tumo.center"),
        ("Dariga", "Хасен Дариға", "dariga.khassen@tumo.center"),
        ("Elmira", "Шайнурова Эльмира", "shainurova.elmira@tumo.center"),
        ("Alen", "Жұмағали Ален Русланұлы", "zhumagali.alen@tumo.center"),
        ("Tahmina", "Қабылбек Тахмина Маратқызы", "t.kabylbek@tumo.center"),
        ("  NAZYM ", "Рысбаева Назым", "rysbayeva.nazym@tumo.center"),
        ("Назым", "Рысбаева Назым", "rysbayeva.nazym@tumo.center"),
        ("Әлинұр", "Манап Әлинұр", "manap.alinur@tumo.center"),
        ("Алинур", "Манап Әлинұр", "manap.alinur@tumo.center"),  # typed without Kazakh letters
        ("Dana T.", "Телжан Дана", "telzhan.dana@tumo.center"),
        ("Dana Kurak", "Дана Құрақ", "kurak.dana@tumo.center"),
        ("Құрақ Дана", "Дана Құрақ", "kurak.dana@tumo.center"),
        ("Ахметова Дана", "Ахметова Дана", "akhmetova.dana@tumo.center"),
        ("Aruzhan Kh.", "Хамзина Аружан", "khamzina.aruzhan@tumo.center"),
        ("Aruzhan T", "Торебек Аружан", "torebek.aruzhan@tumo.center"),
        ("Мырзахмет Аружан", "Мырзахмет Аружан", "aruzhan.myrzakhmet@tumo.center"),
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

        assert coach("сидоров максим") == ("Манап Әлинұр", "manap.alinur@tumo.center")
        assert coach("иванова анна") == ("Dana", None)  # ambiguous: as written, no email
        assert coach("петров олег") == ("Aliya", None)  # not in the list yet


def test_patronymic_prefix_does_not_match_another_coach():
    # "Arman" is only the start of Канбакова Данель Арманқызы's patronymic, not a coach's name.
    assert DIRECTORY.find("Arman") is None
