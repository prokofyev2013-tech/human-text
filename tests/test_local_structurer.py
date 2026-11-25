"""Тесты локального структуратора."""

from app.local_structurer import structure_locally

EXAMPLE_A = (
    "Мне 34 года, я работаю программистом уже 10 лет, но в последнее время не могу "
    "сосредоточиться на коде, постоянно отвлекаюсь, жена говорит что я стал "
    "раздражительным, вчера накричал на сына потому что он громко играл, жена Мария "
    "предлагает пойти к психологу но я не хочу."
)


def test_returns_three_sections() -> None:
    result = structure_locally(EXAMPLE_A)
    assert len(result["sections"]) == 3


def test_sections_have_expected_titles() -> None:
    result = structure_locally(EXAMPLE_A)
    titles = [section["title"] for section in result["sections"]]
    assert titles == [
        "Что происходит",
        "Что, возможно, за этим стоит",
        "О чём поговорить с психологом",
    ]


def test_hypotheses_are_bulleted_and_bounded() -> None:
    result = structure_locally(EXAMPLE_A)
    bullets = result["sections"][1]["bullets"]
    assert 2 <= len(bullets) <= 4


def test_hypotheses_use_modal_wording() -> None:
    result = structure_locally(EXAMPLE_A)
    bullets = result["sections"][1]["bullets"]
    modals = ("возможно", "кажется", "вероятно", "может быть")
    assert all(bullet.lower().startswith(modals) for bullet in bullets)


def test_no_diagnosis_words() -> None:
    result = structure_locally(EXAMPLE_A)
    payload = str(result).lower()
    for forbidden in ("депрессия", "расстройство", "диагноз:"):
        assert forbidden not in payload


def test_generic_text_still_produces_result() -> None:
    result = structure_locally("Просто как-то всё накопилось и стало тяжело.")
    assert len(result["sections"]) == 3
    assert result["sections"][1]["bullets"]
