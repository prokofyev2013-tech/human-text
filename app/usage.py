"""Накопительная статистика запросов для отчётов в VK.

Данные живут только в памяти процесса: ни база, ни логи не пишутся,
чтобы не нарушать анонимность продукта. Счётчик хранит технические
метки (IP, время, токены), а не тексты пользователей.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class RequestRecord:
    """Одна обработанная заявка: кто, когда и сколько токенов."""

    when: str
    source: str
    mode: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    processing_time: float = 0.0
    red_flags: bool = False


@dataclass
class UsageLedger:
    """Потокобезопасный накопитель записей и суммарных показателей."""

    records: list[RequestRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _max_records: int = 1000

    def add(self, record: RequestRecord) -> None:
        with self._lock:
            self.records.append(record)
            if len(self.records) > self._max_records:
                del self.records[: len(self.records) - self._max_records]

    def totals(self) -> dict[str, int]:
        with self._lock:
            return {
                "requests": len(self.records),
                "prompt_tokens": sum(r.prompt_tokens for r in self.records),
                "completion_tokens": sum(r.completion_tokens for r in self.records),
                "total_tokens": sum(r.total_tokens for r in self.records),
                "red_flags": sum(1 for r in self.records if r.red_flags),
            }

    def last(self, count: int = 5) -> list[dict]:
        with self._lock:
            return [asdict(r) for r in self.records[-count:]]

    def reset(self) -> None:
        with self._lock:
            self.records.clear()


ledger = UsageLedger()


def utc_now_label() -> str:
    """Метка времени в UTC для отображения в отчётах."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
