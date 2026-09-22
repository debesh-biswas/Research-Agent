"""OpenAlex discovery adapter."""

import logging
from datetime import date
from typing import Any

from research_agent.discovery.http import request_json
from research_agent.discovery.normalize import (
    normalize_authors,
    normalize_date,
    normalize_doi,
    normalize_text,
    normalize_url,
)
from research_agent.discovery.sources import BaseSource
from research_agent.domain.papers import PaperCandidate, SourceName, SourceReference

_LOGGER = logging.getLogger(__name__)
_URL = "https://api.openalex.org/works"


def _abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """Rebuild an abstract from OpenAlex's inverted index, which is how they return it."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, indexes in inverted_index.items():
        for index in indexes:
            positions[index] = word
    return normalize_text(" ".join(positions[key] for key in sorted(positions)))


class OpenAlexSource(BaseSource):
    """Search OpenAlex works, filtered by publication date."""

    name: SourceName = "openalex"

    def __init__(self, *args: Any, mailto: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._mailto = mailto

    async def search(
        self,
        query: str,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> list[PaperCandidate]:
        candidates: list[PaperCandidate] = []
        cursor = "*"
        while len(candidates) < limit and cursor:
            payload = await request_json(
                self._client,
                _URL,
                params=self._params(query, start_date, end_date, limit - len(candidates), cursor),
                limiter=self._limiter,
                retries=self._retries,
            )
            results = payload.get("results") or []
            for record in results:
                candidate = self._translate(record)
                if candidate is not None:
                    candidates.append(candidate)
                if len(candidates) == limit:
                    break
            if not results:
                break
            cursor = (payload.get("meta") or {}).get("next_cursor") or ""
        return candidates

    def _params(
        self, query: str, start_date: date, end_date: date, remaining: int, cursor: str
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "search": query,
            "filter": (
                f"from_publication_date:{start_date.isoformat()},"
                f"to_publication_date:{end_date.isoformat()}"
            ),
            "per-page": self._page_size(remaining),
            "cursor": cursor,
        }
        if self._mailto:
            # The polite pool gives a contact address better rate limits.
            params["mailto"] = self._mailto
        return params

    def _translate(self, record: Any) -> PaperCandidate | None:
        """Turn one work into a candidate, skipping records too broken to use."""
        if not isinstance(record, dict):
            return None
        title = normalize_text(record.get("display_name") or record.get("title"))
        source_id = normalize_text(record.get("id"))
        if title is None or source_id is None:
            _LOGGER.warning("skipping openalex record without a title or id")
            return None
        location = record.get("primary_location") or {}
        venue = (location.get("source") or {}).get("display_name")
        authors = [
            (authorship.get("author") or {}).get("display_name") or ""
            for authorship in record.get("authorships") or []
            if isinstance(authorship, dict)
        ]
        citations = record.get("cited_by_count")
        return PaperCandidate(
            title=title,
            abstract=_abstract(record.get("abstract_inverted_index")),
            authors=normalize_authors(authors),
            publication_date=normalize_date(record.get("publication_date")),
            discovered_at=self._clock(),
            sources=[
                SourceReference(
                    source=self.name,
                    source_id=source_id,
                    url=normalize_url(location.get("landing_page_url")),
                    pdf_url=normalize_url(location.get("pdf_url")),
                )
            ],
            doi=normalize_doi(record.get("doi")),
            arxiv_id=None,
            venue=normalize_text(venue),
            citation_count=citations if isinstance(citations, int) and citations >= 0 else None,
        )
