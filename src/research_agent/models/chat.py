"""OpenAI-compatible chat-completions provider, used for both local runtimes and NVIDIA NIM."""

import time
from typing import Any

import httpx
from pydantic import BaseModel

from research_agent.config import ModelEndpointSettings
from research_agent.discovery.http import RateLimiter, SourceRequestError, request_json
from research_agent.models.base import ModelMessage, ModelProviderError, ModelResult


class ChatCompletionsProvider:
    """Call a ``/chat/completions`` endpoint, translating failures into model error categories.

    Local runtimes (Ollama, LM Studio, llama.cpp server) and NIM speak the same wire format, so
    they differ only in base URL, model name, and whether an API key is configured.
    """

    name = "chat"

    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: ModelEndpointSettings | None = None,
        retries: int = 0,
    ) -> None:
        self._settings = settings or ModelEndpointSettings()
        self._client = client
        self._limiter = RateLimiter(self._settings.requests_per_second)
        self._retries = retries

    @property
    def model(self) -> str:
        return self._settings.model

    @property
    def configured(self) -> bool:
        """Whether this provider can be used; an endpoint needing a key is unusable without one."""
        return True

    async def generate(
        self,
        task: str,
        messages: list[ModelMessage],
        response_schema: type[BaseModel] | None = None,
    ) -> ModelResult:
        """Send one completion request and return its text with token and latency metadata."""
        del task  # Carried by the caller's log context, not by the wire request.
        body: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [message.model_dump() for message in messages],
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_output_tokens,
        }
        if response_schema is not None:
            body["response_format"] = {"type": "json_object"}

        started = time.monotonic()
        try:
            payload = await request_json(
                self._client,
                f"{self._settings.base_url.rstrip('/')}/chat/completions",
                method="POST",
                json_body=body,
                headers=self._headers(),
                limiter=self._limiter,
                retries=self._retries,
                error_category="MODEL_API_ERROR",
                transient_category="MODEL_TIMEOUT",
            )
        except SourceRequestError as error:
            # The message names the URL and status only; credentials never reach it.
            raise ModelProviderError(f"{self.name} provider failed: {error}", error.category) from (
                error
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        return ModelResult(
            provider=self.name,
            model=self._settings.model,
            text=_content(payload, self.name),
            prompt_tokens=_usage(payload, "prompt_tokens"),
            completion_tokens=_usage(payload, "completion_tokens"),
            latency_ms=latency_ms,
        )

    def _headers(self) -> dict[str, str]:
        """Build request headers per call so the key is never stored on the instance repr."""
        headers = {"content-type": "application/json"}
        if self._settings.api_key:
            headers["authorization"] = f"Bearer {self._settings.api_key}"
        return headers


def _content(payload: dict[str, Any], provider: str) -> str:
    """Read the completion text, treating any unexpected response shape as a provider failure."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ModelProviderError(f"{provider} returned no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise ModelProviderError(f"{provider} returned a choice without text content")
    return content


def _usage(payload: dict[str, Any], field: str) -> int | None:
    usage = payload.get("usage")
    value = usage.get(field) if isinstance(usage, dict) else None
    return value if isinstance(value, int) and value >= 0 else None


class LocalModelProvider(ChatCompletionsProvider):
    """Local Apple-Silicon-friendly runtime exposed over an OpenAI-compatible server."""

    name = "local"


class NvidiaNIMProvider(ChatCompletionsProvider):
    """Optional NVIDIA NIM endpoint; unusable, and therefore skipped, without an API key."""

    name = "nvidia_nim"

    @property
    def configured(self) -> bool:
        return bool(self._settings.api_key)
