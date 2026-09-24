import asyncio

import httpx
import pytest
from pydantic import BaseModel

from research_agent.config import (
    ApplicationSettings,
    ModelSettings,
    NimEndpointSettings,
)
from research_agent.models.base import (
    Capability,
    ModelMessage,
    ModelProviderError,
    ModelResult,
)
from research_agent.models.router import ModelRouter, build_router
from tests.unit.conftest import mock_client

MESSAGES = [ModelMessage(role="user", content="hello")]
STRONG: tuple[Capability, ...] = ("deep_reasoning", "synthesis", "ideation", "report_writing")
LOCAL_ONLY: tuple[Capability, ...] = ("cheap_text", "classification")


class Verdict(BaseModel):
    relevant: bool


class FakeProvider:
    """A provider that answers with a fixed body, or fails, and counts its calls."""

    def __init__(self, name: str, text: str = "ok", error: BaseException | None = None) -> None:
        self.name = name
        self.model = f"{name}-model"
        self.calls = 0
        self._text = text
        self._error = error

    async def generate(
        self,
        task: str,
        messages: list[ModelMessage],
        response_schema: type[BaseModel] | None = None,
    ) -> ModelResult:
        del task, messages, response_schema
        self.calls += 1
        if self._error is not None:
            raise self._error
        return ModelResult(provider=self.name, model=self.model, text=self._text)


def router(
    strong: FakeProvider | None = None, retries: int = 2
) -> tuple[ModelRouter, FakeProvider]:
    local = FakeProvider("local")
    return ModelRouter(local, strong, retries=retries), local


@pytest.mark.parametrize("capability", STRONG)
def test_strong_capabilities_route_to_the_strong_provider(capability: Capability) -> None:
    strong = FakeProvider("nvidia_nim")
    routed, _ = router(strong)
    assert routed.capability_provider(capability) is strong


@pytest.mark.parametrize("capability", LOCAL_ONLY)
def test_cheap_capabilities_route_to_the_local_provider(capability: Capability) -> None:
    routed, local = router(FakeProvider("nvidia_nim"))
    assert routed.capability_provider(capability) is local


@pytest.mark.parametrize("capability", STRONG)
def test_strong_capabilities_route_locally_without_a_strong_provider(
    capability: Capability,
) -> None:
    routed, local = router()
    assert routed.capability_provider(capability) is local


def test_an_unknown_capability_is_rejected() -> None:
    routed, _ = router()
    with pytest.raises(ValueError, match="unknown capability"):
        routed.capability_provider("telepathy")  # type: ignore[arg-type]


def test_the_strong_provider_is_retried_twice_then_local_answers() -> None:
    strong = FakeProvider("nvidia_nim", error=ModelProviderError("NIM is down"))
    routed, local = router(strong)

    result = asyncio.run(routed.generate("synthesis", MESSAGES))

    assert (strong.calls, local.calls) == (3, 1)
    assert result.provider == "local"
    assert result.fell_back is True


def test_a_local_failure_has_nowhere_to_fall_back_to() -> None:
    local = FakeProvider("local", error=ModelProviderError("runtime unreachable"))
    routed = ModelRouter(local)

    with pytest.raises(ModelProviderError):
        asyncio.run(routed.generate("cheap_text", MESSAGES))


def test_a_successful_local_call_is_not_marked_as_a_fallback() -> None:
    routed, local = router(FakeProvider("nvidia_nim"))
    result = asyncio.run(routed.generate("cheap_text", MESSAGES))
    assert (result.provider, result.fell_back, local.calls) == ("local", False, 1)


def test_structured_output_is_validated_and_returned() -> None:
    strong = FakeProvider("nvidia_nim", text='{"relevant": true}')
    routed, _ = router(strong)

    result = asyncio.run(routed.generate("deep_reasoning", MESSAGES, Verdict))

    assert result.parsed == Verdict(relevant=True)
    assert result.text == '{"relevant": true}'


@pytest.mark.parametrize("text", ["not json at all", '{"relevant": "maybe"}'])
def test_malformed_structured_output_raises_without_a_repair_attempt(text: str) -> None:
    strong = FakeProvider("nvidia_nim", text=text)
    routed, local = router(strong)

    with pytest.raises(ModelProviderError, match="Verdict"):
        asyncio.run(routed.generate("synthesis", MESSAGES, Verdict))

    # Invalid output is deterministic, so it is retried on neither provider.
    assert (strong.calls, local.calls) == (1, 0)


def test_cancellation_is_not_swallowed_by_the_fallback_path() -> None:
    strong = FakeProvider("nvidia_nim", error=asyncio.CancelledError())
    routed, local = router(strong)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(routed.generate("ideation", MESSAGES))

    assert (strong.calls, local.calls) == (1, 0)


def test_build_router_uses_nim_only_when_a_key_is_configured() -> None:
    async def run() -> None:
        async with mock_client(lambda request: httpx.Response(200)) as client:
            local_only = build_router(client, ApplicationSettings(strong_model_provider="local"))
            assert local_only.capability_provider("synthesis").name == "local"

            unkeyed = build_router(client, ApplicationSettings(strong_model_provider="nvidia_nim"))
            assert unkeyed.capability_provider("synthesis").name == "local"

            keyed = build_router(
                client,
                ApplicationSettings(
                    strong_model_provider="nvidia_nim",
                    models=ModelSettings(nim=NimEndpointSettings(api_key="nvapi-secret-value")),
                ),
            )
            assert keyed.capability_provider("synthesis").name == "nvidia_nim"

    asyncio.run(run())
