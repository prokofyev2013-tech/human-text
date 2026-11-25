"""Клиент GigaChat API: OAuth-токен, запрос, ретраи, разбор JSON.

Особенности GigaChat (см. dokuments/api/):
- ключ авторизации обменивается на access_token через POST /api/v2/oauth,
  токен живёт 30 минут и переиспользуется;
- для OAuth обязателен заголовок RqUID в формате uuid4;
- ответ chat/completions может быть обёрнут в {"value": {...}};
- сертификат выдан УЦ Минцифры, поэтому проверку TLS можно отключить.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

import httpx

from .config import Settings
from .prompts import RETRY_SUFFIX, SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger("human_text.llm")

# Обновляем токен заранее, чтобы не ловить 401 на границе срока жизни.
_TOKEN_SAFETY_MARGIN = 60


class LLMError(Exception):
    """Базовая ошибка обращения к LLM."""


class LLMTimeout(LLMError):
    """Модель не ответила за отведённое время."""


class LLMBadResponse(LLMError):
    """Модель вернула ответ, который не удалось разобрать."""


class LLMAuthError(LLMError):
    """Не удалось получить токен доступа."""


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json(raw: str) -> dict[str, Any]:
    """Достаёт JSON-объект из ответа модели, даже если он обёрнут в текст."""
    raw = (raw or "").strip()
    if not raw:
        raise LLMBadResponse("Пустой ответ модели")

    candidates: list[str] = []
    block = _JSON_BLOCK_RE.search(raw)
    if block:
        candidates.append(block.group(1))
    candidates.append(raw)

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise LLMBadResponse("В ответе модели нет валидного JSON-объекта")


def _normalize_sections(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Приводит секции к ожидаемому виду, отбрасывая мусор."""
    raw_sections = data.get("sections")
    sections: list[dict[str, Any]] = []

    if isinstance(raw_sections, list):
        for item in raw_sections:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            body = item.get("body")
            bullets = item.get("bullets")

            section: dict[str, Any] = {"title": title}
            if isinstance(bullets, list) and bullets:
                cleaned = [str(b).strip() for b in bullets if str(b).strip()]
                if cleaned:
                    section["bullets"] = cleaned[:4]
            if isinstance(body, str) and body.strip():
                section["body"] = body.strip()

            if "body" in section or "bullets" in section:
                sections.append(section)

    if len(sections) < 2:
        raise LLMBadResponse("Модель вернула слишком мало секций")

    return sections[:3]


def _unwrap(body: dict[str, Any]) -> dict[str, Any]:
    """GigaChat может вернуть ответ внутри {"value": ...}."""
    if isinstance(body.get("value"), dict):
        return body["value"]
    return body


class LLMClient:
    """Клиент GigaChat с кешированием токена и повторными попытками."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    # --- Авторизация -----------------------------------------------------

    async def _get_token(self) -> str:
        """Возвращает действующий access_token, при необходимости обновляет его."""
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        async with self._token_lock:
            # Пока ждали лок, токен мог обновиться в другой задаче.
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {self._settings.llm_api_key}",
            }
            data = {"scope": self._settings.gigachat_scope}

            try:
                async with httpx.AsyncClient(
                    timeout=self._settings.llm_timeout,
                    verify=self._settings.gigachat_verify_ssl,
                ) as client:
                    response = await client.post(
                        self._settings.gigachat_auth_url, headers=headers, data=data
                    )
                    response.raise_for_status()
                    payload = response.json()
            except httpx.TimeoutException as exc:
                raise LLMTimeout("Таймаут при получении токена GigaChat") from exc
            except httpx.HTTPStatusError as exc:
                raise LLMAuthError(
                    f"GigaChat отклонил авторизацию ({exc.response.status_code})"
                ) from exc
            except (httpx.HTTPError, ValueError) as exc:
                raise LLMAuthError("Не удалось получить токен GigaChat") from exc

            token = payload.get("access_token")
            if not token:
                raise LLMAuthError("В ответе OAuth нет access_token")

            expires_at = payload.get("expires_at")
            if isinstance(expires_at, (int, float)):
                # GigaChat отдаёт expires_at в миллисекундах (например,
                # 1793727352725). Определяем разрядность по величине:
                # секундные timestamps заметно меньше 1e11.
                expires_ms = float(expires_at)
                if expires_ms >= 1e11:
                    expires_sec = expires_ms / 1000.0
                else:
                    expires_sec = expires_ms
                remaining = expires_sec - time.time()
                if remaining <= 0:
                    # Срок уже истёк по часам сервиса — берём стандартные 30 минут.
                    remaining = 1800.0
            else:
                remaining = 1800.0

            self._token = str(token)
            self._token_expires_at = time.monotonic() + max(
                remaining - _TOKEN_SAFETY_MARGIN, 30.0
            )
            logger.info("Получен токен GigaChat, действует %.0f с", remaining)
            return self._token

    def _invalidate_token(self) -> None:
        self._token = None
        self._token_expires_at = 0.0

    # --- Основной вызов --------------------------------------------------

    async def structure(self, text: str) -> dict[str, Any]:
        """Возвращает {"sections": [...], "hasRedFlags": bool}."""
        if not self._settings.llm_enabled:
            raise LLMError("LLM не настроена")

        last_error: Exception | None = None
        retries = max(0, self._settings.llm_max_retries)

        for attempt in range(retries + 1):
            suffix = RETRY_SUFFIX if attempt > 0 else ""
            try:
                raw, usage = await self._request(text + suffix)
                data = _extract_json(raw)
                sections = _normalize_sections(data)
                return {
                    "sections": sections,
                    "hasRedFlags": bool(data.get("hasRedFlags")),
                    "usage": usage,
                }
            except LLMTimeout:
                last_error = LLMTimeout("Модель не ответила вовремя")
                logger.warning("LLM timeout, попытка %s из %s", attempt + 1, retries + 1)
            except LLMAuthError as exc:
                last_error = exc
                logger.error("Авторизация GigaChat не удалась: %s", exc)
                break  # повторять бессмысленно: ключ неверный
            except (LLMBadResponse, httpx.HTTPError) as exc:
                last_error = exc
                logger.warning(
                    "LLM ошибка (попытка %s из %s): %s",
                    attempt + 1,
                    retries + 1,
                    type(exc).__name__,
                )

            if attempt < retries:
                await asyncio.sleep(min(2**attempt, 4))

        raise last_error or LLMError("Не удалось получить ответ модели")

    async def _request(self, user_text: str) -> tuple[str, dict[str, int]]:
        """Возвращает (текст ответа модели, расход токенов)."""
        token = await self._get_token()
        url = f"{self._settings.llm_base_url.rstrip('/')}/chat/completions"

        payload = {
            "model": self._settings.llm_model,
            "temperature": self._settings.llm_temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(user_text)},
            ],
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # Без User-Agent GigaChat может вернуть ошибку авторизации.
            "User-Agent": "human-text-app/1.0",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.llm_timeout,
                verify=self._settings.gigachat_verify_ssl,
            ) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 401:
                    # Токен мог истечь раньше времени — обновляем и повторяем один раз.
                    self._invalidate_token()
                    token = await self._get_token()
                    headers["Authorization"] = f"Bearer {token}"
                    response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                body = _unwrap(response.json())
        except httpx.TimeoutException as exc:
            raise LLMTimeout("Таймаут запроса к модели") from exc

        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMBadResponse("Неожиданная структура ответа API") from exc

        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

        usage_raw = body.get("usage")
        usage: dict[str, int] = {}
        if isinstance(usage_raw, dict):
            usage = {
                "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
                "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
                "total_tokens": int(usage_raw.get("total_tokens") or 0),
            }

        return str(content), usage


def build_structured_text(sections: list[dict[str, Any]]) -> str:
    """Склеивает секции в единый текстовый блок (для копирования)."""
    blocks: list[str] = []
    for section in sections:
        title = section.get("title", "").strip()
        if not title:
            continue
        lines = [title]
        body = section.get("body")
        if body:
            lines.append(str(body).strip())
        bullets = section.get("bullets")
        if bullets:
            lines.extend(f"— {str(bullet).strip()}" for bullet in bullets)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
