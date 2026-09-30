"""Capability-based routing so callers never name a vendor, a model, or an endpoint."""

import json
import logging

import httpx
from pydantic import BaseModel, ValidationError

from research_agent.config import ApplicationSettings
from research_agent.models.base import (
    STRONG_CAPABILITIES,
    Capability,
    ModelMessage,
    ModelProvider,
    ModelProviderError,
    ModelResult,
    ModelValidationError,
)
from research_agent.models.chat import LocalModelProvider, NvidiaNIMProvider

_LOGGER = logging.getLogger(__name__)
_CAPABILITIES: frozenset[str] = frozenset(
    {"cheap_text", "classification", *STRONG_CAPABILITIES},
)


class ModelRouter:
    """Send each capability to its provider, degrading to local inference when the strong one fails.

    Screening and deep reasoning use the strong provider when configured.
    """

    def __init__(
        self,
        local: ModelProvider,
        strong: ModelProvider | None = None,
        *,
        retries: int = 2,
    ) -> None:
        self._local = local
        self._strong = strong
        self._retries = retries

    def capability_provider(self, capability: Capability) -> ModelProvider:
        """Resolve a capability to the provider that should serve it."""
        if capability not in _CAPABILITIES:
            raise ValueError(f"unknown capability: {capability}")
        if capability in STRONG_CAPABILITIES and self._strong is not None:
            return self._strong
        return self._local

    async def generate(
        self,
        capability: Capability,
        messages: list[ModelMessage],
        response_schema: type[BaseModel] | None = None,
        task: str | None = None,
    ) -> ModelResult:
        """Run one inference for a capability, retrying the strong provider before falling back."""
        provider = self.capability_provider(capability)
        label = task or capability
        if provider is self._local:
            return _validated(
                await self._local.generate(label, messages, response_schema, capability=capability),
                response_schema,
            )

        # Only call failures are retried here; validation runs after the loop so deterministically
        # malformed output never costs a second call or a pointless fallback.
        last_error: ModelProviderError | None = None
        for attempt in range(self._retries + 1):
            try:
                return _validated(
                    await provider.generate(
                        label, messages, response_schema, capability=capability
                    ),
                    response_schema,
                )
            except ModelValidationError:
                # The task adapter owns one repair attempt, because only it knows how to repair
                # its schema. It may then explicitly ask this router for local fallback.
                raise
            except ModelProviderError as error:
                last_error = error
                _LOGGER.warning(
                    "strong provider attempt failed",
                    extra={
                        "provider": provider.name,
                        "model": provider.model,
                        "node_name": label,
                        "error_type": error.category,
                        "status": f"attempt {attempt + 1}",
                    },
                )

        _LOGGER.warning(
            "falling back to local inference",
            extra={
                "provider": self._local.name,
                "model": self._local.model,
                "node_name": label,
                "error_type": last_error.category if last_error else "MODEL_API_ERROR",
                "status": "fallback",
            },
        )
        result = _validated(
            await self._local.generate(label, messages, response_schema, capability=capability),
            response_schema,
        )
        return result.model_copy(update={"fell_back": True})

    async def generate_local(
        self,
        capability: Capability,
        messages: list[ModelMessage],
        response_schema: type[BaseModel] | None = None,
        task: str | None = None,
    ) -> ModelResult:
        """Run a validated local fallback after a task-specific repair has been exhausted."""
        label = task or capability
        result = _validated(
            await self._local.generate(label, messages, response_schema, capability=capability),
            response_schema,
        )
        return result.model_copy(update={"fell_back": True})


def _validated(result: ModelResult, response_schema: type[BaseModel] | None) -> ModelResult:
    """Validate structured output before it can reach routing or persistence.

    All structured output is validated before it can reach routing or persistence.
    """
    if response_schema is None:
        return result
    try:
        parsed = response_schema.model_validate(_json_object(result.text))
    except (json.JSONDecodeError, ValidationError) as error:
        raise ModelValidationError(
            f"{result.provider} returned output that failed {response_schema.__name__}: {error}"
        ) from error
    return result.model_copy(update={"parsed": parsed})


def _json_object(text: str) -> object:
    """Accept a JSON object even when a chat model wraps it in Markdown prose or fences."""
    content = text.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else ""
        content = content.rsplit("```", 1)[0].strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        if start < 0:
            raise
        value, _ = json.JSONDecoder().raw_decode(content[start:])
        return value


def build_router(client: httpx.AsyncClient, settings: ApplicationSettings) -> ModelRouter:
    """Construct the router a configuration actually enables, warning about an unusable NIM."""
    local = LocalModelProvider(client, settings.models.local)
    strong: ModelProvider | None = None
    if settings.strong_model_provider == "nvidia_nim":
        nim = NvidiaNIMProvider(client, settings.models.nim)
        if nim.configured:
            strong = nim
        else:
            _LOGGER.warning(
                "nvidia_nim selected without an API key; strong work runs locally",
                extra={"provider": "nvidia_nim", "status": "unconfigured"},
            )
    return ModelRouter(local, strong, retries=settings.retries.nim)
