"""Настройки приложения.

Все значения читаются из переменных окружения (файл .env в корне проекта).
Ключ LLM хранится только на сервере и никогда не передаётся на клиент.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

load_dotenv(BASE_DIR / ".env")


def _get_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _get_int(name: str, default: int) -> int:
    raw = _get_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = _get_str(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _gigachat_key() -> str:
    """Ключ авторизации GigaChat для заголовка Basic.

    Если задан готовый LLM_API_KEY, используется он. Иначе ключ собирается
    из GIGACHAT_CLIENT_ID и GIGACHAT_CLIENT_SECRET как Base64("id:secret").
    """
    ready = _get_str("LLM_API_KEY")
    if ready:
        return ready

    client_id = _get_str("GIGACHAT_CLIENT_ID")
    client_secret = _get_str("GIGACHAT_CLIENT_SECRET")
    if client_id and client_secret:
        pair = f"{client_id}:{client_secret}".encode("utf-8")
        return base64.b64encode(pair).decode("ascii")

    return ""


@dataclass(frozen=True)
class Settings:
    """Неизменяемый набор настроек, собранный из окружения."""

    # Ограничения входного текста (ТЗ п. 5.6)
    max_text_length: int = field(default_factory=lambda: _get_int("MAX_TEXT_LENGTH", 5000))
    min_text_length: int = field(default_factory=lambda: _get_int("MIN_TEXT_LENGTH", 10))

    # Ограничение частоты запросов (ТЗ п. 11.3)
    rate_limit_max: int = field(default_factory=lambda: _get_int("RATE_LIMIT_MAX", 5))
    rate_limit_window: int = field(default_factory=lambda: _get_int("RATE_LIMIT_WINDOW", 60))

    # LLM
    llm_provider: str = field(default_factory=lambda: _get_str("LLM_PROVIDER", "gigachat").lower())
    llm_api_key: str = field(default_factory=_gigachat_key)
    llm_base_url: str = field(
        default_factory=lambda: _get_str("LLM_BASE_URL", "https://api.giga.chat/v1")
    )
    llm_model: str = field(default_factory=lambda: _get_str("LLM_MODEL", "GigaChat-2-Max"))
    llm_timeout: float = field(default_factory=lambda: _get_float("LLM_TIMEOUT", 30.0))
    llm_max_retries: int = field(default_factory=lambda: _get_int("LLM_MAX_RETRIES", 2))
    llm_temperature: float = field(default_factory=lambda: _get_float("LLM_TEMPERATURE", 0.4))

    # GigaChat: OAuth (ключ авторизации обменивается на токен доступа)
    gigachat_auth_url: str = field(
        default_factory=lambda: _get_str(
            "GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        )
    )
    gigachat_scope: str = field(
        default_factory=lambda: _get_str("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    )
    # Проверка TLS-сертификата НУЦ Минцифры: у GigaChat собственный УЦ,
    # поэтому по умолчанию проверка отключена.
    gigachat_verify_ssl: bool = field(
        default_factory=lambda: _get_str("GIGACHAT_VERIFY_SSL", "false").lower()
        in ("1", "true", "yes", "on")
    )

    # ВКонтакте: бот сообщества на Long Poll API (отчёты о запросах).
    vk_api_token: str = field(default_factory=lambda: _get_str("VK_API_TOKEN"))
    vk_group_id: int = field(default_factory=lambda: _get_int("VK_GROUP_ID", 0))
    vk_api_version: str = field(
        default_factory=lambda: _get_str("VK_API_VERSION", "5.199")
    )
    # Куда слать уведомление о каждом запросе (peer_id диалога с админом).
    vk_notify_peer_id: int | None = field(
        default_factory=lambda: _get_int("VK_NOTIFY_PEER_ID", 0) or None
    )
    # Список user_id администраторов через запятую (команды в чате бота).
    vk_admin_ids: list[int] = field(
        default_factory=lambda: [
            int(x) for x in _get_str("VK_ADMIN_IDS").split(",") if x.strip().isdigit()
        ]
    )
    # Отправлять уведомление на каждый запрос приложения.
    vk_notify_each_request: bool = field(
        default_factory=lambda: _get_str("VK_NOTIFY_EACH_REQUEST", "true").lower()
        in ("1", "true", "yes", "on")
    )

    @property
    def llm_enabled(self) -> bool:
        """LLM используется, только если задан ключ."""
        return bool(self.llm_api_key)

    @property
    def vk_enabled(self) -> bool:
        """Бот активен, только если заданы токен и id сообщества."""
        return bool(self.vk_api_token and self.vk_group_id)


settings = Settings()
