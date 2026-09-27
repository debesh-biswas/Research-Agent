"""Node-level behavior that the graph tests cannot observe directly."""

import asyncio
from datetime import date
from typing import Any

from research_agent.config import ApplicationSettings, QuerySettings, TopicSettings
from research_agent.discovery.aggregator import DiscoveryResult
from research_agent.workflow import nodes
from research_agent.workflow.state import ResearchState
from tests.unit.conftest import TOPIC_ID, candidate

START = date(2026, 9, 17)
END = date(2026, 9, 27)


class RecordingDiscovery:
    """A discovery aggregator that records the queries it was asked for."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str, start: date, end: date, limit: int) -> DiscoveryResult:
        self.queries.append(query)
        return DiscoveryResult([candidate(doi=f"10.1234/{len(self.queries)}")], {"openalex": 1}, [])


def services(discovery: RecordingDiscovery, max_per_run: int) -> Any:
    settings = ApplicationSettings(queries=QuerySettings(max_per_run=max_per_run))
    topic = TopicSettings.model_validate({"id": TOPIC_ID, "name": "Spatial Intelligence"})

    class Stub:
        pass

    stub = Stub()
    stub.settings = settings  # type: ignore[attr-defined]
    stub.topic = topic  # type: ignore[attr-defined]
    stub.discovery = discovery  # type: ignore[attr-defined]
    return stub


def run_node(node: Any, current: ResearchState) -> dict[str, Any]:
    """Drive one node to completion; `Any` because the graph's node type is opaque to mypy."""
    result: dict[str, Any] = (
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(node(current))
    )
    return result


def state(**overrides: object) -> ResearchState:
    payload: dict[str, object] = {
        "topic_id": TOPIC_ID,
        "period_start": START,
        "period_end": END,
        "run_id": "run1",
    }
    payload.update(overrides)
    return ResearchState.model_validate(payload)


def test_discovery_searches_only_the_configured_number_of_queries() -> None:
    discovery = RecordingDiscovery()
    plan = [f"query {index}" for index in range(8)]

    update = run_node(nodes.discover(services(discovery, max_per_run=3)), state(queries=plan))

    assert discovery.queries == ["query 0", "query 1", "query 2"]
    assert len(update["candidates"]) == 3


def test_discovery_deduplicates_across_queries() -> None:
    class Repeating(RecordingDiscovery):
        async def search(self, query: str, start: date, end: date, limit: int) -> DiscoveryResult:
            self.queries.append(query)
            return DiscoveryResult([candidate(doi="10.1234/same")], {"openalex": 1}, [])

    discovery = Repeating()

    update = run_node(
        nodes.discover(services(discovery, max_per_run=5)), state(queries=["a", "b", "c"])
    )

    assert len(discovery.queries) == 3
    assert len(update["candidates"]) == 1, "the same paper found twice is one candidate"
