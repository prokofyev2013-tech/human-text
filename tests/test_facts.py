"""Тесты сохранения фактов (ТЗ п. 5.2, DoD 3)."""

from app.facts import extract_names, extract_numbers, extract_places, missing_facts
from app.local_structurer import structure_locally


EXAMPLE_A = (
    "Мне 34 года, я работаю программистом уже 10 лет, но в последнее время не могу "
    "сосредоточиться на коде, постоянно отвлекаюсь, жена говорит что я стал "
    "раздражительным, вчера накричал на сына потому что он громко играл, жена Мария "
    "предлагает пойти к психологу но я не хочу."
)

EXAMPLE_B = (
    "Мне 28 лет, последние полгода живу в Москве одна, работа не ладится, друзья все "
    "в другом городе, иногда думаю что лучше бы меня не было."
)


def test_extract_numbers() -> None:
    assert extract_numbers("Мне 34 года, в браке 7 лет, зарплата 120000") == [
        "34",
        "7",
        "120000",
    ]


def test_extract_numbers_keeps_decimals() -> None:
    assert extract_numbers("Платим 2,5 тысячи и 8.5 процента") == ["2,5", "8.5"]


def test_extract_numbers_without_duplicates() -> None:
    assert extract_numbers("Мне 34 года, и снова 34") == ["34"]


def test_extract_names_skips_sentence_start() -> None:
    names = extract_names(EXAMPLE_A)
    assert "Мария" in names
    # Слова из начала предложения не должны попадать в имена.
    assert "Мне" not in names


def test_extract_places_from_example_b() -> None:
    assert "Москве" in extract_places(EXAMPLE_B)


def test_city_is_not_treated_as_person_name() -> None:
    """Город не должен попадать в имена людей."""
    assert "Москве" not in extract_names(EXAMPLE_B)


def test_extract_places_requires_preposition() -> None:
    assert extract_places("Позвонила Мария и рассказала про работу") == []


def test_missing_facts_detects_lost_number() -> None:
    result = missing_facts("Мне 34 года, жена Мария", "Жена и возраст")
    assert result["numbers"] == ["34"]
    assert result["names"] == ["Мария"]


def test_missing_facts_is_empty_when_all_kept() -> None:
    result = missing_facts("Мне 34 года, жена Мария", "Вам 34 года, рядом Мария.")
    assert result == {"numbers": [], "names": [], "places": []}


def test_missing_facts_detects_lost_place() -> None:
    result = missing_facts("Живу в Москве", "Живу одна")
    assert result["places"] == ["Москве"]


def _joined(result: dict) -> str:
    return " ".join(
        [section.get("body", "") for section in result["sections"]]
        + [bullet for section in result["sections"] for bullet in section.get("bullets", [])]
    )


def test_local_result_preserves_facts_of_example_a() -> None:
    result = structure_locally(EXAMPLE_A)
    assert missing_facts(EXAMPLE_A, _joined(result)) == {
        "numbers": [],
        "names": [],
        "places": [],
    }


def test_local_result_preserves_facts_of_example_b() -> None:
    result = structure_locally(EXAMPLE_B)
    assert missing_facts(EXAMPLE_B, _joined(result)) == {
        "numbers": [],
        "names": [],
        "places": [],
    }
