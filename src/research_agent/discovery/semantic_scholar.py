"""Semantic Scholar discovery adapter."""

import logging
from datetime import date
from typing import Any

from research_agent.discovery.http import request_json
from research_agent.discovery.normalize import (
    normalize_arxiv_id,
    normalize_authors,
    normalize_date,
    normalize_doi,
    normalize_text,
    normalize_url,
)
from research_agent.discovery.sources import BaseSource
from research_agent.domain.papers import PaperCandidate, SourceName, SourceReference

_LOGGER = logging.getLogger(__name__)
_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = (
    "title,abstract,authors,publicationDate,year,externalIds,venue,citationCount,openAccessPdf,url"
)
# The search API filters by year only, so the exact window is applied here.
_MAX_PAGE = 100


class SemanticScholarSource(BaseSource):
    """Search Semantic Scholar, applying the exact date window client-side."""

    name: SourceName = "semantic_scholar"

    def __init__(self, *args: Any, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._api_key = api_key

    async def search(
        self,
        query: str,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> list[PaperCandidate]:
        candidates: list[PaperCandidate] = []
        offset = 0
        while len(candidates) < limit:
            payload = await request_json(
                self._client,
                _URL,
                params={
                    "query": query,
                    "fields": _FIELDS,
                    "year": f"{start_date.year}-{end_date.year}",
                    "limit": min(self._page_size(limit - len(candidates)), _MAX_PAGE),
                    "offset": offset,
                },
                headers={"x-api-key": self._api_key} if self._api_key else None,
                limiter=self._limiter,
                retries=self._retries,
            )
            records = payload.get("data") or []
            for record in records:
                candidate = self._translate(record, start_date, end_date)
                if candidate is not None:
                    candidates.append(candidate)
                if len(candidates) == limit:
                    break
            next_offset = payload.get("next")
            if not records or not isinstance(next_offset, int):
                break
            offset = next_offset
        return candidates

    def _translate(self, record: Any, start_date: date, end_date: date) -> PaperCandidate | None:
        if not isinstance(record, dict):
            return None
        title = normalize_text(record.get("title"))
        source_id = normalize_text(record.get("paperId"))
        if title is None or source_id is None:
            _LOGGER.warning("skipping semantic scholar record without a title or id")
            return None
        published = normalize_date(record.get("publicationDate"))
        if published is not None and not start_date <= published <= end_date:
            return None
        external = record.get("externalIds") or {}
        authors = [
            author.get("name") or ""
            for author in record.get("authors") or []
            if isinstance(author, dict)
        ]
        citations = record.get("citationCount")
        return PaperCandidate(
            title=title,
            abstract=normalize_text(record.get("abstract")),
            authors=normalize_authors(authors),
            publication_date=published,
            discovered_at=self._clock(),
            sources=[
                SourceReference(
                    source=self.name,
                    source_id=source_id,
                    url=normalize_url(record.get("url")),
                    pdf_url=normalize_url((record.get("openAccessPdf") or {}).get("url")),
                )
            ],
            doi=normalize_doi(external.get("DOI")),
            arxiv_id=normalize_arxiv_id(external.get("ArXiv")),
            venue=normalize_text(record.get("venue")),
            citation_count=citations if isinstance(citations, int) and citations >= 0 else None,
        )
