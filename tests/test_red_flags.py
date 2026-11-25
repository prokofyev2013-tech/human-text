"""Тесты детекции красных флагов."""

import pytest

from app.red_flags import detect_red_flags


@pytest.mark.parametrize(
    "text",
    [
        "Мне 28 лет, иногда думаю что лучше бы меня не было.",
        "Не вижу смысла жить дальше.",
        "Хочу умереть, сил больше нет.",
        "Я режу себя, когда становится совсем плохо.",
        "Он меня бьет уже второй год.",
        "Меня заставляют молчать об этом.",
        "Ночью накрывает паника, не могу дышать от страха.",
        "Думаю о суициде всё чаще.",
    ],
)
def test_detects_red_flags(text: str) -> None:
    has_flags, topics = detect_red_flags(text)
    assert has_flags is True
    assert topics


@pytest.mark.parametrize(
    "text",
    [
        "Мне 34 года, я работаю программистом и не могу сосредоточиться.",
        "Жена Мария предлагает пойти к психологу, но я не хочу.",
        "Устал от работы, хочется больше отдыхать.",
        "Поругались с братом из-за денег, настроение испорчено.",
    ],
)
def test_does_not_flag_neutral_text(text: str) -> None:
    has_flags, topics = detect_red_flags(text)
    assert has_flags is False
    assert topics == []


def test_empty_text_is_not_flagged() -> None:
    assert detect_red_flags("") == (False, [])
