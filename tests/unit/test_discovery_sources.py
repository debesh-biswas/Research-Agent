import asyncio
from datetime import date
from urllib.parse import parse_qs

import httpx
import pytest

from research_agent.config import SourceSettings
from research_agent.discovery.arxiv import ArxivSource
from research_agent.discovery.http import SourceRequestError
from research_agent.discovery.openalex import OpenAlexSource
from research_agent.discovery.semantic_scholar import SemanticScholarSource
from research_agent.discovery.sources import ResearchSource
from research_agent.domain.papers import PaperCandidate
from tests.unit.conftest import fixed_clock, fixture_text, mock_client

START = date(2026, 9, 12)
END = date(2026, 9, 22)
FAST = SourceSettings(requests_per_second=1000)


def _search(source: ResearchSource, limit: int = 10) -> list[PaperCandidate]:
    return asyncio.run(source.search("spatial intelligence", START, END, limit))


def test_openalex_translates_a_page() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=fixture_text("openalex_page.json"))

    source = OpenAlexSource(mock_client(handler), FAST, clock=fixed_clock, mailto="me@example.org")

    candidates = _search(source)

    assert [candidate.title for candidate in candidates] == [
        "Embodied Spatial Intelligence for Robots",
        "A Survey of Spatial Reasoning",
    ]
    first = candidates[0]
    assert first.doi == "10.1234/abcd"
    assert first.abstract == "Spatial memory helps agents"
    assert first.authors == ["Ada Lovelace", "Alan Turing"]
    assert first.publication_date == date(2026, 9, 18)
    assert first.discovered_at == fixed_clock()
    assert first.venue == "CoRL"
    assert first.citation_count == 4
    assert first.sources[0].source == "openalex"
    assert first.sources[0].pdf_url == "https://example.org/w1.pdf"
    # The malformed third record is skipped, and an ftp url is dropped by normalization.
    assert candidates[1].sources[0].url is None
    query = parse_qs(str(requests[0].url.query.decode()))
    assert query["filter"] == ["from_publication_date:2026-09-12,to_publication_date:2026-09-22"]
    assert query["mailto"] == ["me@example.org"]


def test_openalex_stops_at_the_limit_and_follows_cursors() -> None:
    pages = [
        {
            "meta": {"next_cursor": "second"},
            "results": [
                {"id": f"https://openalex.org/W{index}", "display_name": f"Paper {index}"}
                for index in range(2)
            ],
        },
        {
            "meta": {"next_cursor": None},
            "results": [{"id": "https://openalex.org/W9", "display_name": "Paper 9"}],
        },
    ]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = parse_qs(request.url.query.decode())["cursor"][0]
        seen.append(cursor)
        return httpx.Response(200, json=pages[0] if cursor == "*" else pages[1])

    candidates = _search(OpenAlexSource(mock_client(handler), FAST, clock=fixed_clock), limit=3)

    assert [candidate.title for candidate in candidates] == ["Paper 0", "Paper 1", "Paper 9"]
    assert seen == ["*", "second"]


def test_semantic_scholar_translates_and_filters_by_date() -> None:
    headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        headers.append(request.headers.get("x-api-key"))
        return httpx.Response(200, text=fixture_text("semantic_scholar_page.json"))

    source = SemanticScholarSource(
        mock_client(handler), FAST, clock=fixed_clock, api_key="secret-value"
    )

    candidates = _search(source)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.doi == "10.1234/abcd"
    assert candidate.arxiv_id == "2409.00001"
    assert candidate.citation_count == 6
    assert candidate.sources[0].source_id == "s2-1"
    assert candidate.sources[0].pdf_url == "https://example.org/s2-1.pdf"
    assert headers == ["secret-value"]


def test_semantic_scholar_pages_by_offset() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(parse_qs(request.url.query.decode())["offset"][0])
        if offset == 0:
            return httpx.Response(
                200,
                json={
                    "next": 1,
                    "data": [{"paperId": "a", "title": "First", "publicationDate": "2026-09-13"}],
                },
            )
        return httpx.Response(
            200,
            json={"data": [{"paperId": "b", "title": "Second", "publicationDate": "2026-09-14"}]},
        )

    candidates = _search(
        SemanticScholarSource(mock_client(handler), FAST, clock=fixed_clock), limit=2
    )

    assert [candidate.title for candidate in candidates] == ["First", "Second"]


def test_arxiv_translates_an_atom_feed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=fixture_text("arxiv_page.xml"))

    candidates = _search(ArxivSource(mock_client(handler), FAST, clock=fixed_clock))

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.title == "Embodied Spatial Intelligence for Robots"
    assert candidate.arxiv_id == "2409.00001"
    assert candidate.doi == "10.1234/abcd"
    assert candidate.venue == "CoRL 2026"
    assert candidate.authors == ["Ada Lovelace", "Alan Turing"]
    assert candidate.sources[0].pdf_url == "http://arxiv.org/pdf/2409.00001v2"
    assert candidate.citation_count is None


def test_arxiv_rejects_malformed_xml() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<feed><entry>")

    with pytest.raises(SourceRequestError, match="malformed XML"):
        _search(ArxivSource(mock_client(handler), FAST, clock=fixed_clock))


def test_adapters_return_nothing_for_an_empty_page() -> None:
    def openalex(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [], "meta": {}})

    def semantic_scholar(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    def arxiv(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text='<feed xmlns="http://www.w3.org/2005/Atom"></feed>')

    assert _search(OpenAlexSource(mock_client(openalex), FAST, clock=fixed_clock)) == []
    assert (
        _search(SemanticScholarSource(mock_client(semantic_scholar), FAST, clock=fixed_clock)) == []
    )
    assert _search(ArxivSource(mock_client(arxiv), FAST, clock=fixed_clock)) == []


def test_arxiv_sends_a_descriptive_user_agent() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=fixture_text("arxiv_page.xml"))

    _search(ArxivSource(mock_client(handler), FAST, clock=fixed_clock))

    # arXiv answers anonymous clients with HTTP 406.
    assert requests[0].headers["user-agent"].startswith("research-agent/")
    assert requests[0].headers["accept"] == "application/atom+xml"
    assert str(requests[0].url).startswith("https://export.arxiv.org/api/query")
