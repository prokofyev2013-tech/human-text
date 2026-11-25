"""Диагностический скрипт для проверки подключения к GigaChat API.

Проверяет три шага:
  1. OAuth — обмен ключа авторизации на access_token.
  2. GET /models — список доступных моделей (берём реальное имя).
  3. POST /chat/completions — отправляем тестовый текст и показываем ответ.

Никаких изменений в проекте не вносит. Только чтение и запросы.

Запуск:
  .venv\\Scripts\\python.exe _check_api.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import sys
import time
from datetime import datetime, timezone

import httpx

# Убедимся, что проект на пути и .env загружается.
sys.path.insert(0, ".")
from app.config import settings  # noqa: E402


def _mask(value: str) -> str:
    """Маскируем секретные строки: оставляем первые 4 и последние 4 символа."""
    if not value or len(value) <= 8:
        return "****"
    return value[:4] + "…" + value[-4:]


def _ts(unix: float) -> str:
    """Unix-время → читаемая строка.

    На Windows fromtimestamp() с tz и большими датами падает с OSError,
    поэтому считаем смещение вручную.
    """
    try:
        return datetime.fromtimestamp(int(unix), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except (OSError, OverflowError, ValueError):
        return "(не удалось преобразовать)"


async def step1_oauth() -> str | None:
    """Обмениваем ключ авторизации на access_token. Возвращаем токен или None."""
    print("\n" + "=" * 60)
    print("ШАГ 1/3 — OAuth: обмен ключа на токен доступа")
    print("=" * 60)

    if not settings.llm_api_key:
        print("❌ Ключ не задан. Заполните LLM_API_KEY или GIGACHAT_CLIENT_ID + GIGACHAT_CLIENT_SECRET в .env")
        return None

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(__import__("uuid").uuid4()),
        "Authorization": f"Basic {settings.llm_api_key}",
    }
    data = {"scope": settings.gigachat_scope}

    print(f"  URL  : {settings.gigachat_auth_url}")
    print(f"  Scope: {settings.gigachat_scope}")
    print(f"  Auth : Basic {_mask(settings.llm_api_key)}")
    print()

    try:
        async with httpx.AsyncClient(
            timeout=15,
            verify=settings.gigachat_verify_ssl,
        ) as client:
            resp = await client.post(settings.gigachat_auth_url, headers=headers, data=data)

        print(f"  Статус: {resp.status_code}")

        try:
            payload = resp.json()
        except Exception:
            print(f"  Тело : {resp.text[:500]}")
            if resp.status_code == 403:
                print("  ⚠️  403 Forbidden — проверьте ключ авторизации и scope.")
            elif resp.status_code == 400:
                print("  ⚠️  400 Bad Request — возможно, неверный scope или формат ключа.")
            return None

        if resp.status_code >= 400:
            print(f"  Ошибка: {json.dumps(payload, ensure_ascii=False, indent=2)}")
            return None

        token = payload.get("access_token")
        expires_at = payload.get("expires_at")

        print(f"  access_token : {_mask(str(token)) if token else '(нет)'}")
        if expires_at:
            raw = float(expires_at)
            # GigaChat отдаёт expires_at в миллисекундах.
            sec = raw / 1000.0 if raw >= 1e11 else raw
            remaining = sec - time.time()
            unit = "мс" if raw >= 1e11 else "с"
            print(f"  expires_at   : {int(raw)} ({unit}) -> {_ts(sec)}")
            print(f"  осталось     : {int(remaining)} с (~{int(remaining / 60)} мин)")

        if not token:
            print("  ❌ В ответе OAuth нет access_token")
            return None

        return str(token)

    except httpx.ConnectError as exc:
        print(f"  ❌ Не удалось подключиться: {exc}")
        return None
    except httpx.TimeoutException:
        print("  ❌ Таймаут подключения")
        return None
    except Exception as exc:
        print(f"  ❌ Ошибка: {exc}")
        return None


async def step2_models(token: str) -> str | None:
    """GET /v1/models — возвращаем имя первой доступной модели."""
    print("\n" + "=" * 60)
    print("ШАГ 2/3 — GET /v1/models (список моделей)")
    print("=" * 60)

    url = f"{settings.llm_base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    print(f"  URL: {url}")
    print()

    try:
        async with httpx.AsyncClient(timeout=15, verify=settings.gigachat_verify_ssl) as client:
            resp = await client.get(url, headers=headers)

        print(f"  Статус: {resp.status_code}")

        try:
            body = resp.json()
        except Exception:
            print(f"  Тело : {resp.text[:500]}")
            return None

        if resp.status_code >= 400:
            print(f"  Ошибка: {json.dumps(body, ensure_ascii=False, indent=2)}")
            return None

        data = body.get("data", [])
        if not data:
            print("  ⚠️  models вернул пустой список")
            return None

        print(f"  Найдено моделей: {len(data)}")
        # Показываем до 10 имён.
        for i, m in enumerate(data, 1):
            name = m.get("id", "?")
            mark = "  <= текущая LLM_MODEL" if name == settings.llm_model else ""
            print(f"    {i:2}. {name}{mark}")

        # Проверяем, что настроенная модель реально доступна.
        current = settings.llm_model
        available = [m.get("id") for m in data]
        if current not in available:
            print(f"\n  ⚠️  LLM_MODEL = {current} нет среди доступных моделей.")
            print(f"     Доступные: {', '.join(str(a) for a in available)}")
            print(f"     Поменяйте LLM_MODEL в .env на одно из этих имён.")

        return current

    except Exception as exc:
        print(f"  ❌ Ошибка: {exc}")
        return None


async def step3_chat(token: str, model: str) -> None:
    """POST /v1/chat/completions — отправляем тестовый текст."""
    print("\n" + "=" * 60)
    print("ШАГ 3/3 — POST /v1/chat/completions (тестовый запрос)")
    print("=" * 60)

    url = f"{settings.llm_base_url.rstrip('/')}/chat/completions"

    payload = {
        "model": model,
        "temperature": settings.llm_temperature,
        "messages": [
            {"role": "system", "content": "Ты — полезный AI-ассистент. Отвечай кратко, по-русски."},
            {"role": "user", "content": "Назови три факта о Москве."},
        ],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "human-text-check/1.0",
    }

    print(f"  URL   : {url}")
    print(f"  model : {model}")
    print(f"  prompt: «Назови три факта о Москве.»")
    print()

    try:
        async with httpx.AsyncClient(timeout=30, verify=settings.gigachat_verify_ssl) as client:
            t0 = time.monotonic()
            resp = await client.post(url, json=payload, headers=headers)
            elapsed = time.monotonic() - t0

        print(f"  Статус: {resp.status_code}  (задержка {elapsed:.1f}с)")

        try:
            body = resp.json()
        except Exception:
            print(f"  Тело : {resp.text[:1000]}")
            if resp.status_code == 401:
                print("  ⚠️  401 — токен истёк или неверный scope для этой модели.")
            elif resp.status_code == 422:
                print("  ⚠️  422 — модель не принимает запрос. Попробуй другое LLM_MODEL.")
            return

        if resp.status_code >= 400:
            print(f"  Ошибка: {json.dumps(body, ensure_ascii=False, indent=2)}")
            return

        # GigaChat может обёрнуть в {"value": {...}}.
        if isinstance(body.get("value"), dict):
            body = body["value"]

        choices = body.get("choices", [])
        if not choices:
            print("  ⚠️  choices пустой")
            print(f"  Полный ответ: {json.dumps(body, ensure_ascii=False, indent=2)}")
            return

        msg = choices[0].get("message", {})
        content = msg.get("content", "(пусто)")
        finish = choices[0].get("finish_reason", "?")

        print(f"  finish_reason : {finish}")
        print(f"  response      : {content}")

        usage = body.get("usage", {})
        if usage:
            print(f"  tokens: prompt={usage.get('prompt_tokens')} "
                  f"completion={usage.get('completion_tokens')} "
                  f"total={usage.get('total_tokens')}")

    except httpx.TimeoutException:
        print("  ❌ Таймаут (30 с). Модель не ответила.")
    except Exception as exc:
        print(f"  ❌ Ошибка: {exc}")


async def main() -> int:
    print("Проверка подключения к GigaChat API")
    print(f"  Provider : {settings.llm_provider}")
    print(f"  Base URL : {settings.llm_base_url}")
    print(f"  Model    : {settings.llm_model}")
    print(f"  Auth URL : {settings.gigachat_auth_url}")

    # Шаг 1 — токен
    token = await step1_oauth()
    if not token:
        print("\n🛑 Шаг 1 провален. Дальнейшие шаги пропускаем.")
        print("   Проверьте ключ авторизации и scope в .env.")
        return 1

    # Шаг 2 — модели
    model = await step2_models(token)
    if not model:
        print("\n🛑 Шаг 2 провален. Попытаемся использовать текущую модель.")
        model = settings.llm_model

    # Шаг 3 — чат
    await step3_chat(token, model)

    print("\n" + "=" * 60)
    print("✅ Все три шага пройдены успешно!")
    print("=" * 60)
    print("\nТеперь можно запустить приложение:")
    print(f"  .venv\\Scripts\\python.exe -m uvicorn app.main:app --reload")
    print("Или сразу проверить через браузер:")
    print("  http://127.0.0.1:8000/api/health")
    print("  (llmEnabled должно быть true)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
