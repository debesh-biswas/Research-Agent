"""Turn one configured topic into a bounded, reproducible set of academic search queries."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from research_agent.config import QuerySettings, TopicSettings
from research_agent.discovery.normalize import normalize_text
from research_agent.domain.analysis import WeeklySynthesis
from research_agent.domain.queries import ExpandedQueries, QueryPlan
from research_agent.models.base import ModelMessage, ModelProviderError
from research_agent.models.router import ModelRouter
from research_agent.queries import prompts

_LOGGER = logging.getLogger(__name__)
_MIN_QUERY_LENGTH = 3


def utc_now() -> datetime:
    return datetime.now(UTC)


def base_query(topic: TopicSettings) -> str:
    """The deterministic query used when inference is unavailable, always first in a plan."""
    parts = [topic.name, *topic.keywords[:2]]
    cleaned = [text for text in (normalize_text(part) for part in parts) if text]
    return " ".join(cleaned) or topic.id.replace("_", " ")


class QueryPlanner:
    """Expand a topic semantically, then make the result deterministic and bounded."""

    def __init__(
        self,
        router: ModelRouter,
        settings: QuerySettings | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._router = router
        self._settings = settings or QuerySettings()
        self._clock = clock

    async def plan(
        self,
        topic: TopicSettings,
        history: list[WeeklySynthesis] | None = None,
    ) -> QueryPlan:
        """Produce a plan for one topic; expansion failure degrades, it never raises."""
        anchor = base_query(topic)
        messages = [
            ModelMessage(role="system", content=prompts.SYSTEM_PROMPT),
            ModelMessage(
                role="user",
                content=prompts.render(
                    topic.name,
                    topic.keywords,
                    history or [],
                    self._settings.min_queries,
                    self._settings.max_queries,
                ),
            ),
        ]
        try:
            result = await self._router.generate(
                "cheap_text", messages, ExpandedQueries, task="query_expansion"
            )
        except ModelProviderError as error:
            _LOGGER.warning(
                "query expansion unavailable; using the deterministic base query",
                extra={
                    "topic_id": topic.id,
                    "node_name": "query_expansion",
                    "error_type": error.category,
                    "status": "fallback",
                },
            )
            return self._build(topic, anchor, [], None, None, fell_back=True)

        expanded = result.parsed
        candidates = expanded.queries if isinstance(expanded, ExpandedQueries) else []
        return self._build(topic, anchor, candidates, result.provider, result.model)

    def _build(
        self,
        topic: TopicSettings,
        anchor: str,
        candidates: list[str],
        provider: str | None,
        model: str | None,
        fell_back: bool = False,
    ) -> QueryPlan:
        return QueryPlan(
            topic_id=topic.id,
            queries=self._finalize(anchor, candidates, topic.keywords),
            base_query=anchor,
            prompt_version=prompts.PROMPT_VERSION,
            model_provider=provider,
            model_name=model,
            fell_back=fell_back,
            created_at=self._clock(),
        )

    def _finalize(self, anchor: str, candidates: list[str], keywords: list[str]) -> list[str]:
        """Clean, deduplicate, order, pad, and bound the queries so a plan is reproducible."""
        queries = [anchor]
        seen = {anchor.casefold()}

        def take(values: list[str], ceiling: int) -> None:
            for query in values:
                if len(queries) >= ceiling:
                    return
                if query.casefold() not in seen:
                    seen.add(query.casefold())
                    queries.append(query)

        # Sorting makes the plan independent of the order a model happened to answer in.
        take(sorted(_clean(candidates)), self._settings.max_queries)
        take(sorted(_clean(keywords)), self._settings.min_queries)
        return queries


def _clean(values: list[str]) -> set[str]:
    """Normalize model-supplied text and drop anything too short to be a useful search."""
    cleaned = (normalize_text(value) for value in values if isinstance(value, str))
    return {text for text in cleaned if text and len(text) >= _MIN_QUERY_LENGTH}
