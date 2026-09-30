import pytest

from research_agent.models.base import ModelProviderError, ModelResult
from research_agent.topics.suggest import KeywordSuggestion, suggest_keywords


class Router:
    async def generate(self, *args: object, **kwargs: object) -> ModelResult:
        return ModelResult(
            provider="local",
            model="test-model",
            text="{}",
            parsed=KeywordSuggestion(keywords=["reinforcement learning", "robot grasping"]),
        )


class DeadRouter:
    async def generate(self, *args: object, **kwargs: object) -> ModelResult:
        raise ModelProviderError("down")


@pytest.mark.anyio
async def test_suggest_keywords_returns_the_model_s_list() -> None:
    keywords = await suggest_keywords(Router(), "Robotics", "grasping and manipulation")  # type: ignore[arg-type]

    assert keywords == ["reinforcement learning", "robot grasping"]


@pytest.mark.anyio
async def test_suggest_keywords_degrades_to_empty_when_the_model_is_unavailable() -> None:
    keywords = await suggest_keywords(DeadRouter(), "Robotics", "")  # type: ignore[arg-type]

    assert keywords == []
