"""Общие фикстуры тестов.

Тесты не должны зависеть от наличия ключа в .env и не должны делать
реальные запросы к GigaChat — принудительно переключаем приложение
в локальный режим.
"""

from typing import Any

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _force_local_mode(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Все тесты API идут через локальный структуратор, без сети."""
    offline = Settings(llm_api_key="")
    monkeypatch.setattr("app.main.settings", offline)
    return offline
