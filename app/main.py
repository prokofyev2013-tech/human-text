"""Сборка приложения: маршруты API и раздача статики."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import STATIC_DIR, settings
from .llm_client import LLMBadResponse, LLMClient, LLMError, LLMTimeout, build_structured_text
from .local_structurer import structure_locally
from .models import ErrorResponse, StructureRequest, StructureResponse
from .rate_limit import RateLimiter
from .red_flags import detect_red_flags
from .usage import RequestRecord, ledger, utc_now_label
from .vk_bot import VKBot

logger = logging.getLogger("human_text")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)

limiter = RateLimiter(settings.rate_limit_max, settings.rate_limit_window)
llm_client = LLMClient(settings)
vk_bot = VKBot(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await vk_bot.start()
    try:
        yield
    finally:
        await vk_bot.stop()


app = FastAPI(
    title="Текст по-человечески",
    description="Анонимный инструмент, который помогает разложить сумбурные мысли по полочкам.",
    version="1.0.0",
    lifespan=lifespan,
)


def _client_key(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@app.get("/api/health")
async def health() -> dict[str, object]:
    """Диагностика: доступна ли внешняя модель."""
    return {
        "status": "ok",
        "llmEnabled": settings.llm_enabled,
        "limits": {
            "minTextLength": settings.min_text_length,
            "maxTextLength": settings.max_text_length,
        },
    }


@app.post(
    "/api/structure-text",
    response_model=StructureResponse,
    responses={
        400: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
async def structure_text(payload: StructureRequest, request: Request):
    started = time.perf_counter()

    allowed, retry_after = limiter.allow(_client_key(request))
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Вы отправляете слишком часто. Подождите минуту и попробуйте снова."
            },
            headers={"Retry-After": str(retry_after)},
        )

    text = (payload.text or "").strip()

    if not text:
        return JSONResponse(
            status_code=400,
            content={"error": "Текст пустой. Напишите хотя бы пару предложений."},
        )

    if len(text) < settings.min_text_length:
        return JSONResponse(
            status_code=400,
            content={"error": "Напишите хотя бы пару предложений — так выйдет лучше."},
        )

    if len(text) > settings.max_text_length:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Превышен максимальный размер текста ({settings.max_text_length} знаков)."
            },
        )

    has_red_flags, topics = detect_red_flags(text)

    usage: dict[str, int] = {}
    result: dict
    if settings.llm_enabled:
        try:
            result = await llm_client.structure(text)
            usage = result.get("usage", {}) or {}
        except LLMTimeout:
            logger.error("LLM timeout: обработка прервана")
            return JSONResponse(
                status_code=504,
                content={
                    "error": "Не удалось обработать текст. Попробуйте ещё раз."
                },
            )
        except (LLMBadResponse, LLMError) as exc:
            logger.error("LLM сбой (%s): переход на локальный режим", type(exc).__name__)
            result = structure_locally(text)
        except Exception:  # pragma: no cover - защита от неожиданных сбоев
            logger.exception("Неожиданная ошибка LLM: переход на локальный режим")
            result = structure_locally(text)
    else:
        result = structure_locally(text)

    sections = result["sections"]

    # Красные флаги определяем и локально: LLM может пропустить маркер.
    if has_red_flags:
        result["hasRedFlags"] = True
        logger.info("Обнаружены красные флаги: %s", ", ".join(topics))

    processing_time = round(time.perf_counter() - started, 2)

    # Статистика запроса: кто, когда, сколько токенов (без текста пользователя).
    record = RequestRecord(
        when=utc_now_label(),
        source=_client_key(request),
        mode="llm" if usage else "local",
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        processing_time=processing_time,
        red_flags=bool(result.get("hasRedFlags")),
    )
    ledger.add(record)
    if settings.vk_notify_each_request:
        await vk_bot.notify_request(record)

    return StructureResponse(
        structuredText=build_structured_text(sections),
        sections=sections,
        hasRedFlags=bool(result.get("hasRedFlags")),
        processingTime=processing_time,
    )


# --- Статика ---------------------------------------------------------------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.svg", include_in_schema=False)
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "illustrations" / "mark.svg", media_type="image/svg+xml")
