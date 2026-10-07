import pytest

from app.services.sheets import match_header, matches, name_tokens, parse_tabs


@pytest.mark.parametrize(
    "header, field",
    [
        ("ФИО", "full_name"),
        ("ФИО ученика", "full_name"),
        ("  Full   Name ", "full_name"),
        ("Расписание", "schedule"),
        ("Schedule", "schedule"),
        ("Коуч", "coach_name"),
        ("Coach", "coach_name"),
        ("Кабинет", "room"),
        ("Комната", "room"),
        ("Room", "room"),
        ("Почта", "default_email"),
        ("E-mail", "default_email"),
        ("Пароль", "temp_password"),
        ("Временный пароль", "temp_password"),
        ("Password", "temp_password"),
        ("TUMO ID", "tumo_id"),
        ("ID", "tumo_id"),
        ("Статус", "status"),
    ],
)
def test_header_variants(header, field):
    assert match_header(header) == field


@pytest.mark.parametrize("header", ["Email коуча", "Почта коуча", "ФИО коуча", "№", "Комментарий", ""])
def test_unknown_or_ambiguous_headers_are_not_mapped(header):
    assert match_header(header) is None


@pytest.mark.parametrize(
    "query",
    ["нуртас елмурат", "Елмұрат Нұртас", "ЕЛМУРАТ НУРТАС МЕДЕУУЛЫ", "нурт елму", "Елмурат  Нуртас"],
)
def test_name_matching_is_case_kazakh_order_and_prefix_insensitive(query):
    assert matches(name_tokens(query), name_tokens("Елмұрат Нұртас Медеуұлы"))


@pytest.mark.parametrize("query", ["нуртас нуртас", "нуртас иван", "ртас елмурат"])
def test_name_matching_rejects(query):
    assert not matches(name_tokens(query), name_tokens("Елмұрат Нұртас Медеуұлы"))


def test_multi_tab_parsing_with_title_rows_and_any_column_order():
    raw = {
        "Поток 1": [
            ["Список учащихся"],  # title row above the header
            ["ФИО ученика", "Кабинет", "Расписание", "Коуч", "Почта", "Пароль", "TUMO ID"],
            ["Иван  Петров", "Lab 1", "Пн/Ср 10:00", "Aliya", "ivan@example.com", "P-1", "ID-1"],
        ],
        "Batch 2": [
            ["TUMO ID", "Email", "Full Name", "Schedule", "Coach", "Room", "Password"],
            ["ID-2", "anna@example.com", "Анна Смирнова", "Сб 11:00", "Dana", "Lab 2", "P-2"],
        ],
    }
    learners = {r.full_name: r for r in parse_tabs(raw, source="test").learners}
    assert set(learners) == {"Иван Петров", "Анна Смирнова"}  # double space collapsed
    ivan, anna = learners["Иван Петров"], learners["Анна Смирнова"]
    assert (ivan.schedule, ivan.coach_name, ivan.room) == ("Пн/Ср 10:00", "Aliya", "Lab 1")
    assert (anna.default_email, anna.temp_password, anna.tumo_id) == ("anna@example.com", "P-2", "ID-2")
    assert ivan.tab == "Поток 1" and anna.tab == "Batch 2"
    assert ivan.status_code == "active_schedule"


def test_positional_fallback_skips_notes():
    raw = {
        "No header": [
            ["Иван Петров", "Пн 10:00", "Aliya", "Lab 1", "ivan@example.com", "P-1", "ID-1"],
            ["Напоминание: обновить расписание до пятницы"],
        ]
    }
    learners = parse_tabs(raw, source="test").learners
    assert [r.full_name for r in learners] == ["Иван Петров"]
    assert learners[0].temp_password == "P-1" and learners[0].tumo_id == "ID-1"


def test_duplicate_tumo_id_across_tabs_kept_once():
    header = ["ФИО", "Расписание", "TUMO ID"]
    raw = {"A": [header, ["Иван Петров", "Пн", "ID-1"]], "B": [header, ["Иван Петров", "Вт", "id-1"]]}
    learners = parse_tabs(raw, source="test").learners
    assert len(learners) == 1 and learners[0].schedule == "Пн"


def test_sensitive_columns_and_iin_values_are_dropped():
    raw = {
        "Tab": [
            ["ФИО", "Расписание", "ИИН", "Телефон", "Дата рождения", "Комментарий", "Email коуча"],
            [
                "Иван Петров", "Пн", "000000000000", "+77001234567",
                "01.01.2012", "000000000000", "c@example.com",
            ],
        ]
    }
    snap = parse_tabs(raw, source="test")
    dumped = snap.model_dump_json()
    assert "000000000000" not in dumped and "+77001234567" not in dumped and "01.01.2012" not in dumped
    assert snap.learners[0].extra_info == {"Email коуча": "c@example.com"}


def test_status_column_and_invalid_email():
    raw = {
        "Tab": [
            ["ФИО", "Расписание", "Почта", "Статус"],
            ["Иван Петров", "Пн", "not-an-email", "Неактивен"],
            ["Анна Смирнова", "", "anna@example.com", ""],
        ]
    }
    ivan, anna = parse_tabs(raw, source="test").learners
    assert ivan.status_code == "inactive" and ivan.default_email == ""
    assert anna.status_code == "schedule_pending"
