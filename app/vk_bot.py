"""Бот сообщества ВКонтакте на Long Poll API.

Слушает события сообщества (message_new) и умеет отправлять сообщения.
Две роли:
  1. По команде администратора («статистика») присылает сводку запросов.
  2. Если включён VK_NOTIFY_EACH_REQUEST — на каждый запрос приложения
     шлёт уведомление: кто (IP), когда (UTC) и сколько токенов потрачено.

Токен сообщества и group_id читаются из .env (см. инструкцию в README).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .config import Settings
from .usage import RequestRecord, ledger, utc_now_label

logger = logging.getLogger("human_text.vk")

_API = "https://api.vk.com/method/"

# Команды, на которые бот отвечает в личных сообщениях сообщества.
STATS_COMMANDS = {"статистика", "stats", "/stats", "отчёт"}
RESET_COMMANDS = {"сброс", "reset", "/reset"}


class VKBot:
    """Лёгкий клиент VK с фоновым слушателем Long Poll."""

    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self._api_version = settings.vk_api_version
        self._admin_ids = set(settings.vk_admin_ids)
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return self._s.vk_enabled

    # --- Низкоуровневые вызовы API ---------------------------------------

    async def _api(self, method: str, **params: Any) -> dict[str, Any]:
        assert self._client is not None
        payload = {"v": self._api_version, "access_token": self._s.vk_api_token}
        payload.update({k: v for k, v in params.items() if v is not None})

        resp = await self._client.post(_API + method, data=payload)
        data = resp.json()

        if "error" in data:
            raise RuntimeError(
                f"VK ошибка {data['error'].get('error_code')}: "
                f"{data['error'].get('error_text')}"
            )
        return data.get("response", data)

    async def send_message(self, peer_id: int, text: str) -> None:
        """Отправляет сообщение в диалог сообщества с указанным peer_id."""
        if not text:
            return
        try:
            await self._api(
                "messages.send",
                peer_id=peer_id,
                message=text[:4000],
                random_id=0,
            )
        except Exception as exc:  # noqa: BLE001 - отправка не должна ронять запрос
            logger.error("Не удалось отправить сообщение в VK: %s", exc)

    # --- Long Poll ---------------------------------------------------------

    async def _get_poll_server(self) -> dict[str, Any]:
        return await self._api(
            "groups.getLongPollServer", group_id=self._s.vk_group_id
        )

    async def _listen(self) -> None:
        """Основной цикл: получает обновления и обрабатывает сообщения."""
        assert self._client is not None
        try:
            lp = await self._get_poll_server()
        except Exception as exc:  # noqa: BLE001
            logger.error("VK Long Poll: не удалось получить сервер (%s). Бот не запущен.", exc)
            return

        server, key, ts = lp["server"], lp["key"], str(lp["ts"])
        logger.info("VK Long Poll запущен для сообщества %s", self._s.vk_group_id)

        while True:
            params = {
                "act": "a_check",
                "key": key,
                "ts": ts,
                "wait": 25,
            }
            try:
                resp = await self._client.get(server, params=params, timeout=30)
                update = resp.json()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("VK Long Poll: сетевой сбой (%s), рестарт через 5 с", exc)
                await asyncio.sleep(5)
                try:
                    lp = await self._get_poll_server()
                    server, key, ts = lp["server"], lp["key"], str(lp["ts"])
                except Exception:  # noqa: BLE001
                    pass
                continue

            # Коды ошибок протокола Long Poll → переподключение.
            if update.get("failed"):
                code = update["failed"]
                logger.warning("VK Long Poll: failed=%s, обновляю ключ", code)
                if code == 1:
                    ts = str(update.get("ts", ts))
                else:
                    lp = await self._get_poll_server()
                    server, key, ts = lp["server"], lp["key"], str(lp["ts"])
                continue

            ts = str(update.get("ts", ts))
            for event in update.get("updates", []):
                if event.get("type") == "message_new":
                    # В API >= 5.50 сообщение лежит в object.message,
                    # в старых версиях — прямо в object.
                    obj = event.get("object") or {}
                    message = obj.get("message") if isinstance(obj.get("message"), dict) else obj
                    asyncio.create_task(self._handle_message(message))

    async def _handle_message(self, message: dict[str, Any]) -> None:
        from_id = message.get("from_id")
        peer_id = message.get("peer_id")
        text = (message.get("text") or "").strip().lower()
        # Печатаем идентификаторы, чтобы их было легко скопировать в .env
        # (VK_ADMIN_IDS = user_id, VK_NOTIFY_PEER_ID = peer_id).
        logger.info("VK message: user_id=%s peer_id=%s text=%r", from_id, peer_id, text)
        if not text or peer_id is None:
            return

        if text in STATS_COMMANDS:
            if from_id in self._admin_ids or not self._admin_ids:
                await self.send_message(peer_id, self._format_stats())
            else:
                await self.send_message(
                    peer_id, "Эта команда доступна только администраторам сообщества."
                )
            return

        if text in RESET_COMMANDS:
            if from_id in self._admin_ids:
                ledger.reset()
                await self.send_message(peer_id, "Счётчик запросов обнулён.")
            else:
                await self.send_message(
                    peer_id, "Сброс доступен только администраторам сообщества."
                )

    def _format_stats(self) -> str:
        totals = ledger.totals()
        lines = [
            "Сводка по запросам:",
            f"• Всего запросов: {totals['requests']}",
            f"• Prompt-токены: {totals['prompt_tokens']}",
            f"• Completion-токены: {totals['completion_tokens']}",
            f"• Всего токенов: {totals['total_tokens']}",
            f"• С красными флагами: {totals['red_flags']}",
        ]
        last = ledger.last(3)
        if last:
            lines.append("")
            lines.append("Последние запросы:")
            for r in last:
                lines.append(
                    f"  {r['when']} · {r['source']} · {r['mode']} · "
                    f"{r['total_tokens']} ток."
                )
        return "\n".join(lines)

    # --- Уведомления о запросах -------------------------------------------

    async def notify_request(self, record: RequestRecord) -> None:
        """Шлёт уведомление о запросе в VK_NOTIFY_PEER_ID (если настроено)."""
        if not self.enabled or self._s.vk_notify_peer_id is None:
            return
        text = (
            "Новый запрос в «Текст по-человечески»\n"
            f"• Кто (IP): {record.source}\n"
            f"• Когда (UTC): {record.when}\n"
            f"• Режим: {record.mode}\n"
            f"• Токены: prompt={record.prompt_tokens}, "
            f"completion={record.completion_tokens}, total={record.total_tokens}\n"
            f"• Время обработки: {record.processing_time} с\n"
            f"• Красные флаги: {'да' if record.red_flags else 'нет'}"
        )
        await self.send_message(self._s.vk_notify_peer_id, text)

    # --- Жизненный цикл ---------------------------------------------------

    async def start(self) -> None:
        if not self.enabled:
            return
        self._client = httpx.AsyncClient(timeout=30)
        self._task = asyncio.create_task(self._listen())
        logger.info("VK-бот инициализирован")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client:
            await self._client.aclose()
            self._client = None
