"""Shared pacing, retry, and response-safety layer for academic source adapters."""

import asyncio
import json
import time
from typing import Any

import httpx

from research_agent.domain.runs import ErrorCategory

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_AFTER_SECONDS = 60.0


class SourceRequestError(Exception):
    """A request failed after exhausting its retry budget."""

    def __init__(self, message: str, category: ErrorCategory = "DISCOVERY_ERROR") -> None:
        super().__init__(message)
        self.category: ErrorCategory = category


class RateLimiter:
    """Serialize requests to one provider, holding a minimum interval between them."""

    def __init__(self, requests_per_second: float) -> None:
        self._interval = 1.0 / requests_per_second
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            delay = self._next_allowed - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_allowed = time.monotonic() + self._interval


def _retry_after(response: httpx.Response) -> float | None:
    """Read a ``Retry-After`` delay in seconds, ignoring absent or unusable values."""
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return min(max(float(raw), 0.0), _MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        # HTTP-date form; the backoff schedule is a safe substitute.
        return None


async def request_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    method: str = "GET",
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    limiter: RateLimiter | None = None,
    retries: int = 3,
    backoff_seconds: float = 1.0,
    error_category: ErrorCategory = "DISCOVERY_ERROR",
    transient_category: ErrorCategory = "NETWORK_ERROR",
) -> str:
    """Call a provider URL, retrying only transient failures and honoring ``Retry-After``.

    ponytail: this lives under ``discovery`` because it was written for the source adapters and
    ``models`` is its second consumer. Move it to ``utils/http.py`` when a third one appears.
    """
    last_error = "no attempt was made"
    category: ErrorCategory = error_category
    for attempt in range(retries + 1):
        if limiter is not None:
            await limiter.acquire()
        try:
            response = await client.request(
                method, url, params=params, json=json_body, headers=headers
            )
        except httpx.TimeoutException as error:
            last_error, category = f"timeout: {error}", transient_category
        except httpx.TransportError as error:
            last_error, category = f"transport error: {error}", transient_category
        else:
            if response.status_code < 400:
                return _decoded(response)
            if response.status_code not in _RETRYABLE_STATUS:
                raise SourceRequestError(
                    f"{url} returned HTTP {response.status_code}", error_category
                )
            last_error = f"HTTP {response.status_code}"
            category = "RATE_LIMIT" if response.status_code == 429 else transient_category
            explicit_delay = _retry_after(response)
            if attempt < retries:
                await asyncio.sleep(
                    explicit_delay if explicit_delay is not None else backoff_seconds * 2**attempt
                )
                continue
        if attempt < retries:
            await asyncio.sleep(backoff_seconds * 2**attempt)
    raise SourceRequestError(f"{url} failed after {retries + 1} attempts: {last_error}", category)


def _decoded(response: httpx.Response) -> str:
    """Reject oversized payloads before decoding; provider responses are untrusted input."""
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise SourceRequestError(
            f"{response.request.url} returned {len(response.content)} bytes, over the limit"
        )
    return response.text


async def request_json(
    client: httpx.AsyncClient,
    url: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Call a provider URL and parse a JSON object, treating malformed bodies as a failure."""
    category: ErrorCategory = kwargs.get("error_category", "DISCOVERY_ERROR")
    body = await request_text(client, url, **kwargs)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise SourceRequestError(f"{url} returned invalid JSON: {error}", category) from error
    if not isinstance(payload, dict):
        raise SourceRequestError(
            f"{url} returned {type(payload).__name__}, expected an object", category
        )
    return payload
