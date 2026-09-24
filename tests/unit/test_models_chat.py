import asyncio
import json

import httpx
import pytest

from research_agent.config import ModelEndpointSettings
from research_agent.models.base import ModelMessage, ModelProviderError
from research_agent.models.chat import (
    ChatCompletionsProvider,
    LocalModelProvider,
    NvidiaNIMProvider,
)
from tests.unit.conftest import mock_client

API_KEY = "nvapi-secret-value"
MESSAGES = [ModelMessage(role="user", content="hello")]


def completion(content: str = "ready") -> dict[str, object]:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 2},
    }


def settings(**overrides: object) -> ModelEndpointSettings:
    payload: dict[str, object] = {"base_url": "http://localhost:11434/v1", "model": "qwen3:8b"}
    payload.update(overrides)
    return ModelEndpointSettings.model_validate(payload)


def test_completion_becomes_a_result_with_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "qwen3:8b"
        assert body["messages"] == [{"role": "user", "content": "hello"}]
        assert "response_format" not in body
        return httpx.Response(200, json=completion())

    async def run() -> None:
        async with mock_client(handler) as client:
            result = await LocalModelProvider(client, settings()).generate("probe", MESSAGES)
        assert result.provider == "local"
        assert result.model == "qwen3:8b"
        assert result.text == "ready"
        assert (result.prompt_tokens, result.completion_tokens) == (11, 2)
        assert result.fell_back is False

    asyncio.run(run())


def test_json_schema_requests_a_json_object_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json=completion('{"ok": true}'))

    async def run() -> None:
        async with mock_client(handler) as client:
            await LocalModelProvider(client, settings()).generate(
                "probe", MESSAGES, ModelEndpointSettings
            )

    asyncio.run(run())


def test_authorization_header_is_sent_only_when_a_key_is_configured() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json=completion())

    async def run() -> None:
        async with mock_client(handler) as client:
            await LocalModelProvider(client, settings()).generate("probe", MESSAGES)
            await NvidiaNIMProvider(client, settings(api_key=API_KEY)).generate("probe", MESSAGES)

    asyncio.run(run())
    assert seen == [None, f"Bearer {API_KEY}"]


def test_nim_is_unconfigured_without_a_key() -> None:
    async def run() -> None:
        async with mock_client(lambda request: httpx.Response(200, json=completion())) as client:
            assert NvidiaNIMProvider(client, settings()).configured is False
            assert NvidiaNIMProvider(client, settings(api_key=API_KEY)).configured is True
            assert LocalModelProvider(client, settings()).configured is True

    asyncio.run(run())


def test_server_errors_are_retried_to_the_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500)

    async def run() -> None:
        async with mock_client(handler) as client:
            provider = LocalModelProvider(client, settings(), retries=2)
            with pytest.raises(ModelProviderError) as error:
                await provider.generate("probe", MESSAGES)
        assert error.value.category == "MODEL_TIMEOUT"

    asyncio.run(run())
    assert attempts == 3


def test_client_errors_are_not_retried() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401)

    async def run() -> None:
        async with mock_client(handler) as client:
            provider = NvidiaNIMProvider(client, settings(api_key=API_KEY), retries=2)
            with pytest.raises(ModelProviderError) as error:
                await provider.generate("probe", MESSAGES)
        assert error.value.category == "MODEL_API_ERROR"
        assert API_KEY not in str(error.value)

    asyncio.run(run())
    assert attempts == 1


def test_timeouts_are_reported_as_model_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    async def run() -> None:
        async with mock_client(handler) as client:
            with pytest.raises(ModelProviderError) as error:
                await LocalModelProvider(client, settings()).generate("probe", MESSAGES)
        assert error.value.category == "MODEL_TIMEOUT"

    asyncio.run(run())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": ["not a mapping"]},
    ],
)
def test_unexpected_response_shapes_raise_a_provider_error(payload: dict[str, object]) -> None:
    async def run() -> None:
        async with mock_client(lambda request: httpx.Response(200, json=payload)) as client:
            with pytest.raises(ModelProviderError):
                await LocalModelProvider(client, settings()).generate("probe", MESSAGES)

    asyncio.run(run())


def test_non_json_body_raises_a_provider_error() -> None:
    async def run() -> None:
        async with mock_client(lambda request: httpx.Response(200, text="<html>")) as client:
            with pytest.raises(ModelProviderError) as error:
                await LocalModelProvider(client, settings()).generate("probe", MESSAGES)
        assert error.value.category == "MODEL_API_ERROR"

    asyncio.run(run())


def test_missing_usage_leaves_token_counts_unset() -> None:
    payload = {"choices": [{"message": {"content": "ready"}}]}

    async def run() -> None:
        async with mock_client(lambda request: httpx.Response(200, json=payload)) as client:
            result = await ChatCompletionsProvider(client, settings()).generate("probe", MESSAGES)
        assert result.prompt_tokens is None
        assert result.completion_tokens is None

    asyncio.run(run())


async def _no_sleep(delay: float) -> None:
    del delay
