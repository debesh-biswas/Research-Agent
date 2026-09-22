"""Tests for deterministic metadata normalization."""

from datetime import UTC, date, datetime

import pytest

from research_agent.discovery.normalize import (
    canonical_id,
    normalize_arxiv_id,
    normalize_authors,
    normalize_candidate,
    normalize_date,
    normalize_doi,
    normalize_text,
    normalize_title,
    normalize_url,
)
from research_agent.domain.papers import PaperCandidate, SourceReference


def _candidate(**overrides: object) -> PaperCandidate:
    data: dict[str, object] = {
        "title": "A Paper",
        "discovered_at": datetime(2026, 9, 22, tzinfo=UTC),
        "sources": [SourceReference(source="arxiv", source_id="2401.12345")],
    }
    data.update(overrides)
    return PaperCandidate.model_validate(data)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1234/abcd", "10.1234/abcd"),
        ("https://doi.org/10.1234/abcd", "10.1234/abcd"),
        ("http://dx.doi.org/10.1234/ABCD", "10.1234/abcd"),
        ("doi:10.1234/abcd", "10.1234/abcd"),
        (" 10.1234/abcd ", "10.1234/abcd"),
        ("not-a-doi", None),
        ("10.12/abcd", None),
        (None, None),
    ],
)
def test_normalize_doi_variants(raw: str | None, expected: str | None) -> None:
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("arXiv:2401.12345v3", "2401.12345"),
        ("2401.12345", "2401.12345"),
        ("cs.AI/0701001", "cs.ai/0701001"),
        ("math/0701001", "math/0701001"),
        ("nonsense", None),
        (None, None),
    ],
)
def test_normalize_arxiv_variants(raw: str | None, expected: str | None) -> None:
    assert normalize_arxiv_id(raw) == expected


def test_normalize_text_handles_unicode_and_whitespace() -> None:
    assert normalize_text("  \uff25mbodied\u00a0 spatial   AI \n") == "Embodied spatial AI"
    assert normalize_text("   ") is None


def test_normalize_title_drops_case_and_punctuation() -> None:
    fancy = normalize_title("Deep Learning: A \u201cReview\u201d!")
    assert fancy == normalize_title("deep learning a review")


def test_normalize_authors_deduplicates_preserving_order() -> None:
    assert normalize_authors(["Ada  Lovelace", "ada lovelace", " ", "Alan Turing"]) == [
        "Ada Lovelace",
        "Alan Turing",
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026", date(2026, 1, 1)),
        ("2026-09", date(2026, 9, 1)),
        ("2026-09-22", date(2026, 9, 22)),
        ("2026-09-22T10:30:00+00:00", date(2026, 9, 22)),
        (date(2026, 9, 22), date(2026, 9, 22)),
        (datetime(2026, 9, 22, 10, tzinfo=UTC), date(2026, 9, 22)),
        ("last tuesday", None),
        (None, None),
    ],
)
def test_normalize_date_variants(raw: object, expected: date | None) -> None:
    assert normalize_date(raw) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://example.org/paper", "https://example.org/paper"),
        ("http://example.org", "http://example.org"),
        ("ftp://example.org", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_url_requires_http(raw: str | None, expected: str | None) -> None:
    assert normalize_url(raw) == expected


def test_canonical_id_prefers_doi_then_arxiv_then_hash() -> None:
    with_doi = _candidate(doi="10.1234/abcd", arxiv_id="2401.12345")
    with_arxiv = _candidate(arxiv_id="2401.12345")
    bare = _candidate(authors=["Ada Lovelace"])

    assert canonical_id(with_doi) == "doi_10_1234_abcd"
    assert canonical_id(with_arxiv) == "arxiv_2401_12345"
    assert canonical_id(bare).startswith("title_")
    assert canonical_id(bare) == canonical_id(_candidate(authors=["Ada Lovelace"]))
    assert canonical_id(bare) != canonical_id(_candidate(title="Another Paper"))


def test_normalize_candidate_normalizes_every_field() -> None:
    candidate = normalize_candidate(
        _candidate(
            title="  Embodied   Spatial AI ",
            abstract="  spaced  out  ",
            authors=["  Ada  Lovelace ", "ADA LOVELACE"],
            publication_date=date(2026, 9, 1),
            doi="https://doi.org/10.1234/ABCD",
            arxiv_id="arXiv:2401.12345v2",
            venue=" NeurIPS ",
            sources=[
                SourceReference(
                    source="arxiv",
                    source_id="2401.12345",
                    url="ftp://example.org",
                    pdf_url="https://example.org/a.pdf",
                )
            ],
        )
    )

    assert candidate.title == "Embodied Spatial AI"
    assert candidate.abstract == "spaced out"
    assert candidate.authors == ["Ada Lovelace"]
    assert candidate.publication_date == date(2026, 9, 1)
    assert candidate.doi == "10.1234/abcd"
    assert candidate.arxiv_id == "2401.12345"
    assert candidate.venue == "NeurIPS"
    assert candidate.sources[0].url is None
    assert candidate.sources[0].pdf_url == "https://example.org/a.pdf"
    assert candidate.canonical_id == "doi_10_1234_abcd"
