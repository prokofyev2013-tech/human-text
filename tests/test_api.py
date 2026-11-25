"""Тесты API: валидация, лимиты, красные флаги."""

from fastapi.testclient import TestClient

from app.main import app, limiter

client = TestClient(app)

EXAMPLE_A = (
    "Мне 34 года, я работаю программистом уже 10 лет, но в последнее время не могу "
    "сосредоточиться на коде, постоянно отвлекаюсь, жена говорит что я стал "
    "раздражительным, вчера накричал на сына потому что он громко играл, жена Мария "
    "предлагает пойти к психологу но я не хочу."
)


def setup_function() -> None:
    limiter.reset()


def test_health_reports_limits() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["limits"]["maxTextLength"] == 5000
    assert payload["limits"]["minTextLength"] == 10


def test_index_page_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Текст по-человечески" in response.text


def test_structure_returns_sections() -> None:
    response = client.post("/api/structure-text", json={"text": EXAMPLE_A})
    assert response.status_code == 200

    payload = response.json()
    assert payload["hasRedFlags"] is False
    assert len(payload["sections"]) == 3
    assert payload["structuredText"]
    assert isinstance(payload["processingTime"], float)


def test_structure_keeps_numbers_and_names() -> None:
    payload = client.post("/api/structure-text", json={"text": EXAMPLE_A}).json()
    combined = payload["structuredText"].lower()
    assert "34" in combined
    assert "10" in combined
    assert "мария" in combined


def test_red_flag_text_sets_flag_and_returns_result() -> None:
    text = "Мне 28 лет, иногда думаю что лучше бы меня не было."
    payload = client.post("/api/structure-text", json={"text": text}).json()

    assert payload["hasRedFlags"] is True
    assert payload["sections"], "результат должен формироваться даже при красных флагах"


def test_empty_text_is_rejected() -> None:
    response = client.post("/api/structure-text", json={"text": "   "})
    assert response.status_code == 400
    assert "error" in response.json()


def test_too_short_text_is_rejected() -> None:
    response = client.post("/api/structure-text", json={"text": "привет"})
    assert response.status_code == 400


def test_text_over_limit_is_rejected() -> None:
    response = client.post("/api/structure-text", json={"text": "а" * 5001})
    assert response.status_code == 400
    assert "5000" in response.json()["error"]


def test_text_at_limit_is_accepted() -> None:
    response = client.post("/api/structure-text", json={"text": "а" * 5000})
    assert response.status_code == 200


def test_rate_limit_returns_429() -> None:
    text = "Мне 30 лет, всё накопилось и стало тяжело."
    for _ in range(5):
        assert client.post("/api/structure-text", json={"text": text}).status_code == 200

    response = client.post("/api/structure-text", json={"text": text})
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_missing_field_is_rejected() -> None:
    response = client.post("/api/structure-text", json={})
    assert response.status_code == 422
