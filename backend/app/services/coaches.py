"""Coach directory: turns the sheet's coach cell ("Alinur", "Nazym", "Манап Әлинұр", an email)
into the coach's full name in Russian/Kazakh and their work email.

The list lives in data/coaches.json ([{"name": ..., "email": ...}]) so it can be extended
without code changes. Matching is deliberately conservative: a sheet value must identify exactly
one coach, otherwise the raw value is shown without an email — a wrong coach's email is worse
than none. Several coaches share first names (Дана, Аружан), so those need a surname in the sheet.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .sheets import name_tokens

log = logging.getLogger(__name__)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_TOKEN = 2


def _latin(token: str) -> str:
    """Smooth over common Latin transliteration differences: kh/h, y/i, doubled letters."""
    t = token.replace("kh", "h").replace("y", "i")
    return re.sub(r"(.)\1+", r"\1", t)


def _norm(tokens: list[str]) -> list[str]:
    return [_latin(t) if t.isascii() else t for t in tokens]


# Cyrillic -> Latin for name tokens already folded by name_tokens (Kazakh letters -> Russian).
_TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z", "и": "i",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "y",
    "ь": "", "э": "e", "ю": "yu", "я": "ya",
})


def _transliterate(tokens: list[str]) -> list[str]:
    """Latin forms of Cyrillic name tokens, so "Tahmina" finds Тахмина even if her email doesn't."""
    return [_latin(t.translate(_TRANSLIT)) for t in tokens if not t.isascii()]


def _token_matches(word: str, coach_tokens: tuple[str, ...]) -> bool:
    """Whole-word match; a single letter is an initial and matches a word's start.

    Whole words keep "Arman" from matching the patronymic "Арманқызы" of another coach.
    """
    if len(word) == 1:
        return any(t.startswith(word) for t in coach_tokens)
    return word in coach_tokens


@dataclass(frozen=True)
class Coach:
    name: str
    email: str
    tokens: tuple[str, ...]  # Cyrillic name tokens + Latin tokens from the email's local part


class CoachDirectory:
    def __init__(self, coaches: list[Coach] | None = None):
        self.coaches = coaches or []
        self._by_email = {c.email: c for c in self.coaches}

    @classmethod
    def from_entries(cls, entries: list[dict]) -> "CoachDirectory":
        coaches = []
        for e in entries:
            name = " ".join(str(e.get("name", "")).split())
            email = str(e.get("email", "")).strip().lower()
            if not name or not _EMAIL.match(email):
                continue
            local = re.split(r"[._\-+]", email.split("@")[0])
            cyrillic = _norm(name_tokens(name))
            latin = _norm([t for t in local if len(t) >= MIN_TOKEN]) + _transliterate(cyrillic)
            tokens = tuple(dict.fromkeys(cyrillic + latin))
            coaches.append(Coach(name=name, email=email, tokens=tokens))
        return cls(coaches)

    @classmethod
    def load(cls, path: Path) -> "CoachDirectory":
        """Missing or broken file -> empty directory (coach names shown as written in the sheet)."""
        try:
            directory = cls.from_entries(json.loads(path.read_text(encoding="utf-8")))
            log.info("Loaded %d coaches from %s", len(directory.coaches), path)
            return directory
        except FileNotFoundError:
            return cls()
        except Exception:
            log.exception("Ignoring unreadable coach directory %s", path)
            return cls()

    def find(self, raw: str) -> Coach | None:
        """The single coach `raw` identifies, or None if unknown or ambiguous."""
        value = " ".join((raw or "").split())
        if not value:
            return None
        if _EMAIL.match(value):
            return self._by_email.get(value.lower())
        tokens = _norm(name_tokens(value))
        # Single letters count only as initials next to a real name: "Dana T." -> Телжан Дана.
        if not any(len(t) >= MIN_TOKEN for t in tokens):
            return None
        wanted = tokens
        hits = [c for c in self.coaches if all(_token_matches(w, c.tokens) for w in wanted)]
        return hits[0] if len(hits) == 1 else None

    def resolve(self, raw: str) -> tuple[str, str | None]:
        """(name to show, email or None). Unknown/ambiguous values are shown as written."""
        coach = self.find(raw)
        return (coach.name, coach.email) if coach else (" ".join((raw or "").split()), None)
