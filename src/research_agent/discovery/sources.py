"""The provider-neutral discovery interface and the state every adapter shares."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Protocol

import httpx

from research_agent.config import SourceSettings
from research_agent.discovery.http import RateLimiter
from research_agent.domain.papers import PaperCandidate, SourceName


def utc_now() -> datetime:
    return datetime.now(UTC)


class ResearchSource(Protocol):
    """One academic search provider, independent of its wire format."""

    name: SourceName

    async def search(
        self,
        query: str,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> list[PaperCandidate]: ...


class BaseSource:
    """Client, pacing, retry budget, and clock shared by every adapter."""

    name: SourceName

    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: SourceSettings | None = None,
        retries: int = 3,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._client = client
        self._settings = settings or SourceSettings()
        self._limiter = RateLimiter(self._settings.requests_per_second)
        self._retries = retries
        self._clock = clock

    def _page_size(self, remaining: int) -> int:
        return max(1, min(remaining, self._settings.max_page_size))
