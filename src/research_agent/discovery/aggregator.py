"""Fan-out across discovery sources with failure isolation and a per-run cache."""

import asyncio
import logging
from collections.abc import Sequence
from datetime import date

import httpx

from research_agent.config import ApplicationSettings, DiscoverySettings
from research_agent.discovery.arxiv import ArxivSource
from research_agent.discovery.deduplicate import deduplicate
from research_agent.discovery.http import SourceRequestError
from research_agent.discovery.openalex import OpenAlexSource
from research_agent.discovery.semantic_scholar import SemanticScholarSource
from research_agent.discovery.sources import ResearchSource
from research_agent.domain.papers import PaperCandidate, SourceName
from research_agent.domain.runs import ErrorRecord

_LOGGER = logging.getLogger(__name__)

_CacheKey = tuple[str, str, str, str, int]


class DiscoveryResult:
    """Combined candidates plus per-source counts and the errors that were tolerated."""

    def __init__(
        self,
        candidates: list[PaperCandidate],
        counts: dict[str, int],
        errors: list[ErrorRecord],
    ) -> None:
        self.candidates = candidates
        self.counts = counts
        self.errors = errors


class DiscoveryAggregator:
    """Search every enabled source concurrently and merge the results."""

    def __init__(
        self,
        sources: Sequence[ResearchSource],
        concurrency: int = 3,
        settings: ApplicationSettings | None = None,
        run_id: str = "unscheduled",
    ) -> None:
        self._sources = list(sources)
        self._semaphore = asyncio.Semaphore(concurrency)
        self._settings = settings or ApplicationSettings()
        self._run_id = run_id
        self._cache: dict[_CacheKey, list[PaperCandidate]] = {}

    async def search(
        self,
        query: str,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> DiscoveryResult:
        """Return one deduplicated candidate set; a failing source never discards the others."""
        results = await asyncio.gather(
            *(
                self._search_one(source, query, start_date, end_date, limit)
                for source in self._sources
            ),
            return_exceptions=True,
        )

        candidates: list[PaperCandidate] = []
        counts: dict[str, int] = {}
        errors: list[ErrorRecord] = []
        for source, result in zip(self._sources, results, strict=True):
            if isinstance(result, BaseException):
                errors.append(self._to_error(source.name, result))
                counts[source.name] = 0
                continue
            counts[source.name] = len(result)
            candidates.extend(result)

        merged = deduplicate(candidates, self._settings.deduplication)
        return DiscoveryResult(merged[:limit], counts, errors)

    async def _search_one(
        self,
        source: ResearchSource,
        query: str,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> list[PaperCandidate]:
        key: _CacheKey = (
            source.name,
            query,
            start_date.isoformat(),
            end_date.isoformat(),
            limit,
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        async with self._semaphore:
            found = await source.search(query, start_date, end_date, limit)
        self._cache[key] = found
        return found

    def _to_error(self, source_name: SourceName, error: BaseException) -> ErrorRecord:
        category = error.category if isinstance(error, SourceRequestError) else "DISCOVERY_ERROR"
        _LOGGER.warning(
            "discovery source failed",
            extra={"provider": source_name, "error_type": category, "status": "degraded"},
        )
        return ErrorRecord(
            run_id=self._run_id,
            node="discover",
            category=category,
            message=f"{source_name}: {error}",
            recoverable=True,
        )


def build_sources(
    client: httpx.AsyncClient,
    settings: ApplicationSettings,
    enabled: DiscoverySettings,
) -> list[ResearchSource]:
    """Construct the adapters a topic has enabled, each with its own pacing."""
    sources: list[ResearchSource] = []
    retries = settings.retries.academic_apis
    if enabled.openalex:
        sources.append(
            OpenAlexSource(
                client,
                settings.sources.openalex,
                retries=retries,
                mailto=settings.sources.openalex_mailto,
            )
        )
    if enabled.semantic_scholar:
        sources.append(
            SemanticScholarSource(
                client,
                settings.sources.semantic_scholar,
                retries=retries,
                api_key=settings.sources.semantic_scholar_api_key,
            )
        )
    if enabled.arxiv:
        sources.append(ArxivSource(client, settings.sources.arxiv, retries=retries))
    return sources
