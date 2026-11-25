"""Модели данных API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StructureRequest(BaseModel):
    text: str = Field(..., description="Текст пользователя")


class Section(BaseModel):
    """Секция структурированного результата."""

    title: str
    body: str | None = None
    bullets: list[str] | None = None


class StructureResponse(BaseModel):
    structuredText: str
    sections: list[Section]
    hasRedFlags: bool
    processingTime: float


class ErrorResponse(BaseModel):
    error: str
