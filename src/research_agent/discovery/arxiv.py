"""arXiv discovery adapter."""

import logging
from datetime import date
from typing import Any
from xml.etree import ElementTree

from research_agent.discovery.http import SourceRequestError, request_text
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
_URL = "https://export.arxiv.org/api/query"
# arXiv answers requests without a descriptive agent and Atom accept header with HTTP 406.
_HEADERS = {
    "user-agent": "research-agent/0.1 (local research assistant)",
    "accept": "application/atom+xml",
}
_ATOM = "{http://www.w3.org/2005/Atom}"
_ARXIV = "{http://arxiv.org/schemas/atom}"


class ArxivSource(BaseSource):
    """Search the arXiv Atom API, applying the date window client-side."""

    name: SourceName = "arxiv"

    async def search(
        self,
        query: str,
        start_date: date,
        end_date: date,
        limit: int,
    ) -> list[PaperCandidate]:
        candidates: list[PaperCandidate] = []
        start = 0
        while len(candidates) < limit:
            page_size = self._page_size(limit - len(candidates))
            body = await request_text(
                self._client,
                _URL,
                params={
                    "search_query": f"all:{query}",
                    "start": start,
                    "max_results": page_size,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
                headers=_HEADERS,
                limiter=self._limiter,
                retries=self._retries,
            )
            entries = _entries(body)
            for entry in entries:
                candidate = self._translate(entry, start_date, end_date)
                if candidate is not None:
                    candidates.append(candidate)
                if len(candidates) == limit:
                    break
            if len(entries) < page_size:
                break
            start += page_size
        return candidates

    def _translate(
        self, entry: ElementTree.Element, start_date: date, end_date: date
    ) -> PaperCandidate | None:
        title = normalize_text(_text(entry, f"{_ATOM}title"))
        entry_id = normalize_text(_text(entry, f"{_ATOM}id"))
        if title is None or entry_id is None:
            _LOGGER.warning("skipping arxiv entry without a title or id")
            return None
        arxiv_id = normalize_arxiv_id(entry_id.rsplit("/abs/", 1)[-1])
        published = normalize_date((_text(entry, f"{_ATOM}published") or "")[:10])
        if published is not None and not start_date <= published <= end_date:
            return None
        authors = [
            _text(author, f"{_ATOM}name") or "" for author in entry.findall(f"{_ATOM}author")
        ]
        pdf_url = next(
            (
                link.get("href")
                for link in entry.findall(f"{_ATOM}link")
                if link.get("title") == "pdf"
            ),
            None,
        )
        return PaperCandidate(
            title=title,
            abstract=normalize_text(_text(entry, f"{_ATOM}summary")),
            authors=normalize_authors(authors),
            publication_date=published,
            discovered_at=self._clock(),
            sources=[
                SourceReference(
                    source=self.name,
                    source_id=arxiv_id or entry_id,
                    url=normalize_url(entry_id),
                    pdf_url=normalize_url(pdf_url),
                )
            ],
            doi=normalize_doi(_text(entry, f"{_ARXIV}doi")),
            arxiv_id=arxiv_id,
            venue=normalize_text(_text(entry, f"{_ARXIV}journal_ref")),
            citation_count=None,
        )


def _entries(body: str) -> list[ElementTree.Element]:
    """Parse an Atom feed. Malformed XML is a source failure, not a crash."""
    # ponytail: stdlib ElementTree resolves no external entities, which covers the realistic
    # risk here; swap in defusedxml if arXiv feeds ever need hardening against entity bombs.
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError as error:
        raise SourceRequestError(f"arxiv returned malformed XML: {error}") from error
    return root.findall(f"{_ATOM}entry")


def _text(element: Any, path: str) -> str | None:
    found = element.find(path)
    return None if found is None else found.text
