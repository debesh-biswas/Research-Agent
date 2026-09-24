from conftest import candidate

from research_agent.documents.urls import pdf_candidates
from research_agent.domain.papers import SourceReference


def reference(source: str, pdf_url: str | None, source_id: str = "1") -> SourceReference:
    return SourceReference.model_validate(
        {"source": source, "source_id": source_id, "pdf_url": pdf_url}
    )


def test_arxiv_is_derived_and_tried_first() -> None:
    paper = candidate(
        arxiv_id="2409.00001",
        sources=[reference("openalex", "https://example.org/a.pdf")],
    )

    assert pdf_candidates(paper) == [
        "https://arxiv.org/pdf/2409.00001",
        "https://example.org/a.pdf",
    ]


def test_sources_are_tried_in_a_fixed_order() -> None:
    paper = candidate(
        sources=[
            reference("arxiv", "https://example.org/c.pdf"),
            reference("semantic_scholar", "https://example.org/b.pdf"),
            reference("openalex", "https://example.org/a.pdf"),
        ]
    )

    assert pdf_candidates(paper) == [
        "https://example.org/a.pdf",
        "https://example.org/b.pdf",
        "https://example.org/c.pdf",
    ]


def test_the_same_url_from_two_sources_is_requested_once() -> None:
    paper = candidate(
        sources=[
            reference("openalex", "https://example.org/same.pdf"),
            reference("semantic_scholar", "https://example.org/same.pdf", source_id="2"),
        ]
    )

    assert pdf_candidates(paper) == ["https://example.org/same.pdf"]


def test_insecure_urls_are_upgraded() -> None:
    paper = candidate(sources=[reference("openalex", "http://example.org/a.pdf")])

    assert pdf_candidates(paper) == ["https://example.org/a.pdf"]


def test_unfetchable_schemes_are_dropped() -> None:
    paper = candidate(
        sources=[
            reference("openalex", "ftp://example.org/a.pdf"),
            reference("semantic_scholar", "file:///etc/passwd", source_id="2"),
            reference("arxiv", "https://example.org/ok.pdf", source_id="3"),
        ]
    )

    assert pdf_candidates(paper) == ["https://example.org/ok.pdf"]


def test_a_paper_with_no_pdf_url_yields_nothing() -> None:
    assert pdf_candidates(candidate(sources=[reference("openalex", None)])) == []


def test_a_url_without_a_host_is_rejected() -> None:
    assert pdf_candidates(candidate(sources=[reference("openalex", "https:///a.pdf")])) == []
