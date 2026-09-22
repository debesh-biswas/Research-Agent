import asyncio
from datetime import date

from conftest import fixed_clock

from research_agent.discovery.aggregator import DiscoveryAggregator, DiscoveryResult
from research_agent.discovery.http import SourceRequestError
from research_agent.domain.papers import PaperCandidate, SourceName, SourceReference

START = date(2026, 9, 12)
END = date(2026, 9, 22)


class FakeSource:
    """A source that records its calls, so cache hits and concurrency are observable."""

    def __init__(
        self,
        name: SourceName,
        candidates: list[PaperCandidate] | None = None,
        error: Exception | None = None,
        inflight: list[int] | None = None,
        peak: list[int] | None = None,
    ) -> None:
        self.name = name
        self._candidates = candidates or []
        self._error = error
        self.calls = 0
        self._inflight = inflight
        self._peak = peak

    async def search(
        self, query: str, start_date: date, end_date: date, limit: int
    ) -> list[PaperCandidate]:
        self.calls += 1
        if self._inflight is not None and self._peak is not None:
            self._inflight.append(1)
            self._peak.append(len(self._inflight))
            await asyncio.sleep(0)
            self._inflight.pop()
        if self._error is not None:
            raise self._error
        return self._candidates


def _candidate(name: SourceName, title: str, doi: str | None = None) -> PaperCandidate:
    return PaperCandidate(
        title=title,
        authors=["Ada Lovelace"],
        discovered_at=fixed_clock(),
        sources=[SourceReference(source=name, source_id=f"{name}-1")],
        doi=doi,
    )


def _search(aggregator: DiscoveryAggregator, limit: int = 10) -> DiscoveryResult:
    return asyncio.run(aggregator.search("spatial intelligence", START, END, limit))


def test_the_same_paper_from_three_sources_merges_once() -> None:
    sources = [
        FakeSource("openalex", [_candidate("openalex", "Embodied Spatial AI", "10.1234/abcd")]),
        FakeSource(
            "semantic_scholar",
            [_candidate("semantic_scholar", "Embodied Spatial AI", "10.1234/abcd")],
        ),
        FakeSource("arxiv", [_candidate("arxiv", "A Different Paper")]),
    ]

    result = _search(DiscoveryAggregator(sources))

    assert len(result.candidates) == 2
    merged = next(c for c in result.candidates if c.doi == "10.1234/abcd")
    assert [reference.source for reference in merged.sources] == ["openalex", "semantic_scholar"]
    assert result.counts == {"openalex": 1, "semantic_scholar": 1, "arxiv": 1}
    assert result.errors == []


def test_one_failing_source_does_not_discard_the_others() -> None:
    sources = [
        FakeSource("openalex", [_candidate("openalex", "Embodied Spatial AI")]),
        FakeSource("semantic_scholar", error=SourceRequestError("429 forever", "RATE_LIMIT")),
        FakeSource("arxiv", [_candidate("arxiv", "Another Paper")]),
    ]

    result = _search(DiscoveryAggregator(sources, run_id="run-1"))

    assert len(result.candidates) == 2
    assert result.counts["semantic_scholar"] == 0
    assert [error.category for error in result.errors] == ["RATE_LIMIT"]
    assert result.errors[0].run_id == "run-1"
    assert "semantic_scholar" in result.errors[0].message


def test_all_sources_failing_yields_errors_and_no_candidates() -> None:
    sources = [
        FakeSource("openalex", error=SourceRequestError("down")),
        FakeSource("semantic_scholar", error=RuntimeError("unexpected")),
        FakeSource("arxiv", error=SourceRequestError("timeout", "NETWORK_ERROR")),
    ]

    result = _search(DiscoveryAggregator(sources))

    assert result.candidates == []
    assert [error.category for error in result.errors] == [
        "DISCOVERY_ERROR",
        "DISCOVERY_ERROR",
        "NETWORK_ERROR",
    ]


def test_an_identical_query_is_served_from_the_run_cache() -> None:
    source = FakeSource("arxiv", [_candidate("arxiv", "Embodied Spatial AI")])
    aggregator = DiscoveryAggregator([source])

    first = _search(aggregator)
    second = _search(aggregator)

    assert source.calls == 1
    assert [c.canonical_id for c in first.candidates] == [c.canonical_id for c in second.candidates]


def test_concurrency_never_exceeds_the_configured_bound() -> None:
    def run_with(concurrency: int) -> int:
        inflight: list[int] = []
        peak: list[int] = []
        names: tuple[SourceName, ...] = ("openalex", "semantic_scholar", "arxiv")
        sources = [FakeSource(name, [], inflight=inflight, peak=peak) for name in names]
        _search(DiscoveryAggregator(sources, concurrency=concurrency))
        assert all(source.calls == 1 for source in sources)
        return max(peak)

    assert run_with(1) == 1
    assert run_with(3) == 3


def test_the_limit_is_applied_to_the_merged_set() -> None:
    sources = [
        FakeSource(
            "openalex",
            [_candidate("openalex", f"Paper {index}", f"10.1234/{index}") for index in range(5)],
        )
    ]

    result = _search(DiscoveryAggregator(sources), limit=3)

    assert len(result.candidates) == 3
