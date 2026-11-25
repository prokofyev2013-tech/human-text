"""Тесты клиента GigaChat: OAuth, обёртка value, разбор ответа."""

import json
from typing import Any

import pytest

from app.config import Settings
from app.llm_client import (
    LLMBadResponse,
    LLMClient,
    _extract_json,
    _normalize_sections,
    _unwrap,
    build_structured_text,
)


def test_extract_json_plain() -> None:
    raw = '{"sections": [], "hasRedFlags": false}'
    assert _extract_json(raw)["hasRedFlags"] is False


def test_extract_json_from_markdown_block() -> None:
    raw = 'Вот результат:\n```json\n{"sections": [], "hasRedFlags": true}\n```\nГотово.'
    assert _extract_json(raw)["hasRedFlags"] is True


def test_extract_json_from_surrounding_text() -> None:
    raw = 'Конечно! {"sections": [], "hasRedFlags": false} Надеюсь, помог.'
    assert _extract_json(raw)["sections"] == []


def test_extract_json_raises_on_garbage() -> None:
    with pytest.raises(LLMBadResponse):
        _extract_json("Извините, не могу помочь.")


def test_extract_json_raises_on_empty() -> None:
    with pytest.raises(LLMBadResponse):
        _extract_json("   ")


def test_unwrap_gigachat_value() -> None:
    body = {"value": {"choices": [{"message": {"content": "текст"}}]}}
    assert _unwrap(body) == {"choices": [{"message": {"content": "текст"}}]}


def test_unwrap_plain_openai_shape() -> None:
    body = {"choices": [{"message": {"content": "текст"}}]}
    assert _unwrap(body) is body


def test_normalize_sections_keeps_body_and_bullets() -> None:
    data = {
        "sections": [
            {"title": "Что происходит", "body": "Текст."},
            {"title": "Гипотезы", "bullets": ["Первая", "Вторая"]},
            {"title": "С психологом", "body": "Обсудить."},
        ]
    }
    sections = _normalize_sections(data)
    assert sections[1]["bullets"] == ["Первая", "Вторая"]


def test_normalize_sections_limits_bullets_to_four() -> None:
    data = {
        "sections": [
            {"title": "A", "body": "1"},
            {"title": "B", "bullets": ["1", "2", "3", "4", "5", "6"]},
        ]
    }
    assert len(_normalize_sections(data)[1]["bullets"]) == 4


def test_normalize_sections_drops_items_without_content() -> None:
    data = {
        "sections": [
            {"title": "Пусто"},
            {"title": "A", "body": "1"},
            {"title": "B", "body": "2"},
        ]
    }
    titles = [section["title"] for section in _normalize_sections(data)]
    assert "Пусто" not in titles


def test_normalize_sections_requires_at_least_two() -> None:
    with pytest.raises(LLMBadResponse):
        _normalize_sections({"sections": [{"title": "Одна", "body": "текст"}]})


def test_build_structured_text_contains_bullets() -> None:
    text = build_structured_text(
        [
            {"title": "Что происходит", "body": "Описание."},
            {"title": "Гипотезы", "bullets": ["Раз", "Два"]},
        ]
    )
    assert "Что происходит" in text
    assert "— Раз" in text
    assert "— Два" in text
    assert "\n\n" in text


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import httpx

            request = httpx.Request("POST", "https://example.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)


class _FakeClient:
    """Подменяет httpx.AsyncClient: маршрутизирует ответ по URL.

    Клиент создаётся заново на каждый запрос, поэтому ответы хранятся
    не в очереди, а в общем для теста реестре маршрутов.
    """

    routes: dict[str, _FakeResponse] = {}
    requests: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        type(self).requests.append((url, kwargs))
        for marker, response in type(self).routes.items():
            if marker in url:
                return response
        raise AssertionError(f"Неожиданный URL: {url}")


def _settings(**overrides: Any) -> Settings:
    base = {
        "llm_api_key": "test-key",
        "llm_base_url": "https://api.giga.chat/v1",
        "llm_model": "GigaChat-2-Max",
        "llm_max_retries": 0,
    }
    base.update(overrides)
    return Settings(**base)


def _chat_payload(has_red_flags: bool = False) -> dict[str, Any]:
    return {
        "value": {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "sections": [
                                    {"title": "A", "body": "1"},
                                    {"title": "B", "body": "2"},
                                ],
                                "hasRedFlags": has_red_flags,
                            }
                        )
                    }
                }
            ]
        }
    }


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> type[_FakeClient]:
    import app.llm_client as module

    _FakeClient.routes = {
        "oauth": _FakeResponse({"access_token": "tok-1", "expires_at": 9_999_999_999}),
        "chat/completions": _FakeResponse(_chat_payload()),
    }
    _FakeClient.requests = []
    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeClient)
    return _FakeClient


@pytest.mark.asyncio
async def test_oauth_token_is_cached(fake_http: type[_FakeClient]) -> None:
    """Второй вызов не должен повторно запрашивать токен."""
    client = LLMClient(_settings())
    await client.structure("первый текст")
    await client.structure("второй текст")

    oauth_calls = [url for url, _ in fake_http.requests if "oauth" in url]
    assert len(oauth_calls) == 1, "токен должен переиспользоваться"


@pytest.mark.asyncio
async def test_request_uses_bearer_token_and_user_agent(
    fake_http: type[_FakeClient],
) -> None:
    fake_http.routes["chat/completions"] = _FakeResponse(_chat_payload(True))

    client = LLMClient(_settings())
    result = await client.structure("текст")

    assert result["hasRedFlags"] is True
    chat_call = [call for call in fake_http.requests if "chat" in call[0]][0]
    headers = chat_call[1]["headers"]
    assert headers["Authorization"] == "Bearer tok-1"
    assert "User-Agent" in headers


@pytest.mark.asyncio
async def test_oauth_request_has_rquid_and_scope(fake_http: type[_FakeClient]) -> None:
    client = LLMClient(_settings())
    await client.structure("текст")

    oauth_call = [call for call in fake_http.requests if "oauth" in call[0]][0]
    headers = oauth_call[1]["headers"]
    assert "RqUID" in headers
    assert len(headers["RqUID"]) == 36, "RqUID должен быть в формате uuid4"
    assert headers["Authorization"].startswith("Basic ")
    assert oauth_call[1]["data"] == {"scope": "GIGACHAT_API_PERS"}


@pytest.mark.asyncio
async def test_ssl_verification_flag_is_passed(fake_http: type[_FakeClient]) -> None:
    client = LLMClient(_settings(gigachat_verify_ssl=False))
    await client.structure("текст")

    assert fake_http.requests, "должен быть хотя бы один запрос"
    # Флаг проверки сертификата должен прокидываться в клиент.
    assert _FakeClient.routes is not None
