import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from research_agent.config import QuerySettings, TopicSettings
from research_agent.domain.analysis import WeeklySynthesis
from research_agent.domain.queries import ExpandedQueries, QueryPlan
from research_agent.models.base import (
    Capability,
    ModelMessage,
    ModelProviderError,
    ModelResult,
    ModelValidationError,
)
from research_agent.queries import prompts
from research_agent.queries.planner import QueryPlanner, base_query

EXPANDED = ["spatial reasoning benchmarks", "embodied navigation agents", "3d scene understanding"]


class FakeRouter:
    """Stands in for ``ModelRouter``, recording the prompt and returning canned expansions."""

    def __init__(self, queries: list[str] | None = None, error: Exception | None = None) -> None:
        self.messages: list[ModelMessage] = []
        self.calls = 0
        self._queries = queries or []
        self._error = error

    async def generate(
        self,
        capability: Capability,
        messages: list[ModelMessage],
        response_schema: type[BaseModel] | None = None,
        task: str | None = None,
    ) -> ModelResult:
        del capability, response_schema, task
        self.calls += 1
        self.messages = messages
        if self._error is not None:
            raise self._error
        return ModelResult(
            provider="local",
            model="qwen3:8b",
            text="{}",
            parsed=ExpandedQueries(queries=self._queries),
        )


def topic(**overrides: object) -> TopicSettings:
    payload: dict[str, object] = {
        "id": "spatial_intelligence",
        "name": "Spatial Intelligence",
        "keywords": ["spatial reasoning", "embodied agents"],
    }
    payload.update(overrides)
    return TopicSettings.model_validate(payload)


def plan(
    router: FakeRouter,
    topic_settings: TopicSettings | None = None,
    settings: QuerySettings | None = None,
    history: list[WeeklySynthesis] | None = None,
) -> QueryPlan:
    planner = QueryPlanner(
        router,  # type: ignore[arg-type]
        settings,
        clock=lambda: datetime(2026, 9, 22, tzinfo=UTC),
    )
    return asyncio.run(planner.plan(topic_settings or topic(), history))


def test_the_base_query_comes_from_the_topic_alone() -> None:
    assert base_query(topic()) == "Spatial Intelligence spatial reasoning embodied agents"
    assert base_query(topic(name="Robotics", keywords=[])) == "Robotics"
    # An unusable name still yields a query, because a plan must never be empty.
    assert base_query(topic(name=" ", keywords=[])) == "spatial intelligence"


def test_a_plan_leads_with_the_base_query_and_keeps_the_expansions() -> None:
    result = plan(FakeRouter(EXPANDED))

    assert result.queries[0] == result.base_query
    assert set(EXPANDED) <= set(result.queries)
    assert (result.model_provider, result.model_name) == ("local", "qwen3:8b")
    assert result.fell_back is False
    assert result.prompt_version == prompts.PROMPT_VERSION


def test_duplicates_blanks_and_case_variants_collapse() -> None:
    noisy = ["spatial reasoning", "Spatial  Reasoning", "  ", "", "ab", "spatial reasoning"]

    result = plan(FakeRouter(noisy), topic(keywords=[]))

    folded = [query.casefold() for query in result.queries]
    assert folded.count("spatial reasoning") == 1
    assert "ab" not in result.queries
    assert all(query.strip() for query in result.queries)


def test_output_is_truncated_to_the_configured_ceiling() -> None:
    many = [f"query number {index:02d}" for index in range(40)]

    result = plan(FakeRouter(many), settings=QuerySettings(min_queries=2, max_queries=6))

    assert len(result.queries) == 6
    assert result.queries[0] == result.base_query


def test_a_short_expansion_is_padded_from_keywords() -> None:
    result = plan(
        FakeRouter(["spatial reasoning benchmarks"]),
        topic(keywords=["embodied agents", "scene graphs", "visual navigation"]),
        QuerySettings(min_queries=4, max_queries=20),
    )

    assert len(result.queries) >= 4
    assert "scene graphs" in result.queries


@pytest.mark.parametrize(
    "error",
    [ModelProviderError("runtime unreachable"), ModelValidationError("bad structured output")],
)
def test_inference_failure_degrades_to_the_deterministic_plan(error: Exception) -> None:
    result = plan(FakeRouter(error=error))

    assert result.fell_back is True
    assert result.queries[0] == result.base_query
    # Nothing in a fallback plan came from a model; the rest is the topic's own keywords.
    assert set(result.queries[1:]) <= set(topic().keywords)
    assert (result.model_provider, result.model_name) == (None, None)


def test_an_empty_expansion_still_produces_a_usable_plan() -> None:
    result = plan(FakeRouter([]), topic(keywords=[]))

    assert result.queries == [result.base_query]
    assert result.fell_back is False


def test_unicode_topics_survive_normalization() -> None:
    result = plan(FakeRouter([]), topic(name="Räumliche Intelligenz  —  Übersicht", keywords=[]))

    assert result.queries == ["Räumliche Intelligenz — Übersicht"]


def test_history_and_keywords_reach_the_prompt() -> None:
    router = FakeRouter(EXPANDED)
    history = [WeeklySynthesis(major_developments=["diffusion policies for manipulation"])]

    plan(router, history=history)

    rendered = router.messages[-1].content
    assert "diffusion policies for manipulation" in rendered
    assert "spatial reasoning" in rendered
    assert router.messages[0].role == "system"


def test_the_same_inputs_produce_an_identical_plan() -> None:
    shuffled = list(reversed(EXPANDED))

    first = plan(FakeRouter(EXPANDED))
    second = plan(FakeRouter(shuffled))

    assert first == second
