import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

import httpx
import pytest

from research_agent.discovery.http import (
    MAX_RESPONSE_BYTES,
    RateLimiter,
    SourceRequestError,
    request_json,
    request_text,
)
from tests.unit.conftest import mock_client

T = TypeVar("T")


def _run(coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def test_a_successful_request_returns_the_body() -> None:
    client = mock_client(lambda request: httpx.Response(200, text="ok"))

    assert _run(request_text(client, "https://example.org")) == "ok"


def test_a_rate_limited_response_is_retried_then_succeeds() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, text="slow down")
        return httpx.Response(200, text="ok")

    result = _run(request_text(mock_client(handler), "https://example.org", backoff_seconds=0))

    assert result == "ok"
    assert len(attempts) == 2


def test_retry_after_is_honored_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        if not delays:
            return httpx.Response(429, headers={"retry-after": "7"}, text="slow down")
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    assert _run(request_text(mock_client(handler), "https://example.org")) == "ok"
    assert delays == [7.0]


def test_an_unparseable_retry_after_falls_back_to_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    def handler(request: httpx.Request) -> httpx.Response:
        if not delays:
            return httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"})
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    assert _run(request_text(mock_client(handler), "https://example.org")) == "ok"
    assert delays == [1.0]


def test_the_retry_ceiling_is_respected_exactly() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503)

    with pytest.raises(SourceRequestError) as error:
        _run(
            request_text(mock_client(handler), "https://example.org", retries=3, backoff_seconds=0)
        )

    assert len(attempts) == 4
    assert error.value.category == "NETWORK_ERROR"


def test_a_client_error_is_not_retried() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(404)

    with pytest.raises(SourceRequestError):
        _run(request_text(mock_client(handler), "https://example.org", backoff_seconds=0))

    assert len(attempts) == 1


def test_timeouts_are_retried_then_reported_as_network_errors() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectTimeout("too slow", request=request)

    with pytest.raises(SourceRequestError) as error:
        _run(
            request_text(mock_client(handler), "https://example.org", retries=2, backoff_seconds=0)
        )

    assert len(attempts) == 3
    assert error.value.category == "NETWORK_ERROR"


def test_oversized_responses_are_rejected_before_parsing() -> None:
    body = "x" * (MAX_RESPONSE_BYTES + 1)
    client = mock_client(lambda request: httpx.Response(200, text=body))

    with pytest.raises(SourceRequestError, match="over the limit"):
        _run(request_text(client, "https://example.org"))


def test_invalid_json_is_a_source_failure() -> None:
    client = mock_client(lambda request: httpx.Response(200, text="not json"))

    with pytest.raises(SourceRequestError, match="invalid JSON"):
        _run(request_json(client, "https://example.org"))


def test_a_json_array_is_rejected() -> None:
    client = mock_client(lambda request: httpx.Response(200, json=[1, 2]))

    with pytest.raises(SourceRequestError, match="expected an object"):
        _run(request_json(client, "https://example.org"))


def test_the_rate_limiter_spaces_requests() -> None:
    async def scenario() -> float:
        limiter = RateLimiter(requests_per_second=50)
        loop = asyncio.get_running_loop()
        started = loop.time()
        await limiter.acquire()
        await limiter.acquire()
        return loop.time() - started

    assert asyncio.run(scenario()) >= 0.02
