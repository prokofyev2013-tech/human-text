"""Извлечение фактов из текста: имена, числа, ключевые маркеры.

Используется и локальным структуратором, и тестами на сохранность фактов
(ТЗ п. 5.2, DoD 3).
"""

from __future__ import annotations

import re

# Числа: «34», «10 лет», «8 000», «2,5», «полгода» не берём — только цифры.
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")

# Слова с заглавной буквы, кроме начала предложения — кандидаты в имена.
_CAPITALIZED_RE = re.compile(r"(?<!^)(?<!\. )(?<![!?] )\b([А-ЯЁ][а-яё]{2,})\b")

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

# Служебные слова, которые часто попадают в «заглавные» ложно.
_STOP_CAPITALS = {
    "Мне",
    "Меня",
    "Мой",
    "Моя",
    "Мои",
    "Я",
    "Он",
    "Она",
    "Они",
    "Но",
    "А",
    "И",
    "В",
    "На",
    "С",
    "У",
    "Не",
    "Это",
    "Что",
    "Как",
    "Когда",
    "Если",
    "Потому",
    "Вчера",
    "Сегодня",
    "Завтра",
    "Последние",
    "Иногда",
    "Постоянно",
    "Очень",
    "Уже",
    "Ещё",
    "Еще",
    "Все",
    "Всё",
    "Всегда",
    "Никогда",
    "Просто",
    "Тогда",
    "Сейчас",
}


def extract_numbers(text: str) -> list[str]:
    """Все числовые значения в порядке появления, без дублей."""
    seen: list[str] = []
    for match in _NUMBER_RE.findall(text or ""):
        if match not in seen:
            seen.append(match)
    return seen


# Предлоги, после которых заглавное слово почти наверняка обозначает место.
_PLACE_PREPOSITIONS = (
    "в", "во", "из", "от", "до", "на", "под", "над", "около", "возле",
    "через", "у", "к", "по",
)
_PLACE_PREP_RE = re.compile(
    r"\b(" + "|".join(_PLACE_PREPOSITIONS) + r")\s+([А-ЯЁ][а-яё-]{2,})\b"
)


def extract_places(text: str) -> list[str]:
    """Названия мест: заглавные слова после пространственных предлогов."""
    if not text:
        return []

    places: list[str] = []
    for match in _PLACE_PREP_RE.finditer(text):
        word = match.group(2)
        if word in _STOP_CAPITALS:
            continue
        if word not in places:
            places.append(word)
    return places


def extract_names(text: str) -> list[str]:
    """Собственные имена людей: заглавные слова не в начале предложения.

    Названия мест сюда не попадают — они извлекаются отдельно.
    """
    if not text:
        return []

    places = set(extract_places(text))
    names: list[str] = []
    for match in _CAPITALIZED_RE.finditer(text):
        word = match.group(1)
        if word in _STOP_CAPITALS or word in places:
            continue
        if word not in names:
            names.append(word)
    return names


def split_sentences(text: str) -> list[str]:
    """Разбивает текст на предложения, отбрасывая пустые фрагменты."""
    if not text:
        return []
    parts = [part.strip(" \t—–-") for part in _SENTENCE_SPLIT_RE.split(text)]
    return [part for part in parts if part]


def normalize(text: str) -> str:
    """Приводит текст к виду для сравнения: нижний регистр, схлопнутые пробелы."""
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def missing_facts(source: str, result: str) -> dict[str, list[str]]:
    """Возвращает факты исходника, которых нет в результате.

    Сравнение мягкое: числа ищутся как подстрока, имена и места — без учёта регистра.
    """
    result_norm = normalize(result)
    missing_numbers = [
        number for number in extract_numbers(source) if number not in result_norm
    ]
    missing_names = [
        name for name in extract_names(source) if normalize(name) not in result_norm
    ]
    missing_places = [
        place for place in extract_places(source) if normalize(place) not in result_norm
    ]
    return {"numbers": missing_numbers, "names": missing_names, "places": missing_places}
