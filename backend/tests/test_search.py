"""Name search: Kazakh letters, three-word names, partial words, typos and look-alike letters.

All names are fake.
"""

import pytest

from app.models import LearnerRecord
from app.services.sheets import _one_edit, find_learners, name_tokens


def rec(full_name: str) -> LearnerRecord:
    return LearnerRecord(tokens=name_tokens(full_name), full_name=full_name, status_code="active_schedule")


PEOPLE = [
    rec("Тұрдықұл Ғарифулла Рахманқұлұлы"),
    rec("Сұлтанбек Аяла Серікқызы"),
    rec("Әбдіманаф Санжар Қанатұлы"),
    rec("Иванова Анна"),  # no patronymic in the sheet
    rec("Иванова Анна Петровна"),
    rec("Ғалымжан Әмір Сабыржанұлы"),
    rec("Тoребек Дана"),  # Latin "o" typed by mistake in the sheet
]


def find(query: str) -> list[str]:
    tokens = [t for t in name_tokens(query) if len(t) >= 3]  # as the endpoint does
    if len(tokens) < 2:  # the endpoint answers "need_full_name" before searching
        return []
    return [r.full_name for r in find_learners(tokens, PEOPLE)]


@pytest.mark.parametrize("query", [
    "Тұрдықұл Ғарифулла Рахманқұлұлы",  # exact, with Kazakh letters
    "Турдыкул Гарифулла Рахманкулулы",  # same, typed with Russian letters
    "Турдыкул Гарифулла",
    "Гарифулла Турдыкул",  # any order
    "ТҰРДЫҚҰЛ ҒАРИФУЛЛА",  # capitals
    "Тур Гар",  # 3-letter beginnings
    "Тұр Ғар Рах",
    "Гарифулла Рахманкулулы",  # first name + patronymic
    "Турдыкул Гарифула",  # one typo (missing letter)
    "Турдыкул Гарифулла Рахманович",  # wrong patronymic: two of three words match
])
def test_finds_turdykul(query):
    assert find(query) == ["Тұрдықұл Ғарифулла Рахманқұлұлы"]


@pytest.mark.parametrize("query, expected", [
    ("Сұлтанбек Аяла", ["Сұлтанбек Аяла Серікқызы"]),
    ("Султанбек Аяла Серикkызы", ["Сұлтанбек Аяла Серікқызы"]),  # Latin "k" inside a Cyrillic word
    ("Абдиманаф Санжар", ["Әбдіманаф Санжар Қанатұлы"]),
    ("Галымжан Амир", ["Ғалымжан Әмір Сабыржанұлы"]),
])
def test_kazakh_and_russian_spellings(query, expected):
    assert find(query) == expected


def test_three_words_when_sheet_has_only_two():
    # Both "Иванова Анна" rows match two words; the one with the patronymic matches all three.
    assert find("Иванова Анна Петровна") == ["Иванова Анна Петровна"]
    assert sorted(find("Иванова Анна")) == ["Иванова Анна", "Иванова Анна Петровна"]


def test_latin_lookalikes_in_the_sheet_are_folded():
    assert find("Торебек Дана") == ["Тoребек Дана"]
    assert name_tokens("Тoребек") == name_tokens("Торебек")
    assert name_tokens("Dana Akhmetova") == ["dana", "akhmetova"]  # pure Latin names untouched


def test_two_word_queries_still_need_both_words():
    assert find("Турдыкул Петров") == []
    assert find("Гарифулла") == []  # one word is never enough (anti-enumeration)


def test_short_words_need_exact_prefixes():
    assert find("Тыр Гар") == []  # 3 letters: no typo tolerance


@pytest.mark.parametrize("a, b, ok", [
    ("гарифула", "гарифулла", True), ("гарифулла", "гарифула", True), ("гаритулла", "гарифулла", True),
    ("гарфиулла", "гарифулла", True), ("гарифулла", "гарифулла", True), ("гарфулла", "гарифулла", True),
    ("гаррифула", "гарифулла", False), ("абвгд", "абвгдеж", False),
])
def test_one_edit(a, b, ok):
    assert _one_edit(a, b) is ok


def test_invisible_characters_in_the_sheet_are_ignored():
    assert name_tokens("Тұрды​құл Ғари­фулла") == name_tokens("Турдыкул Гарифулла")
