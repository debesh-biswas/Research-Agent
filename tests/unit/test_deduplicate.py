"""Tests for candidate deduplication and merge rules."""

import random
from datetime import UTC, date, datetime

from research_agent.config import DeduplicationSettings
from research_agent.discovery.deduplicate import deduplicate
from research_agent.domain.papers import PaperCandidate, SourceReference

_DISCOVERED = datetime(2026, 9, 22, tzinfo=UTC)


def _candidate(
    title: str = "Embodied Spatial Intelligence for Robots",
    source: str = "openalex",
    source_id: str = "W1",
    **overrides: object,
) -> PaperCandidate:
    data: dict[str, object] = {
        "title": title,
        "discovered_at": _DISCOVERED,
        "sources": [SourceReference.model_validate({"source": source, "source_id": source_id})],
    }
    data.update(overrides)
    return PaperCandidate.model_validate(data)


def test_same_doi_from_three_sources_collapses_to_one() -> None:
    candidates = [
        _candidate(source="openalex", source_id="W1", doi="10.1234/abcd"),
        _candidate(source="semantic_scholar", source_id="S1", doi="https://doi.org/10.1234/abcd"),
        _candidate(source="arxiv", source_id="2401.12345", doi="DOI:10.1234/ABCD"),
    ]

    merged = deduplicate(candidates)

    assert len(merged) == 1
    assert [reference.source for reference in merged[0].sources] == [
        "arxiv",
        "openalex",
        "semantic_scholar",
    ]
    assert merged[0].canonical_id == "doi_10_1234_abcd"


def test_same_arxiv_id_without_doi_merges() -> None:
    candidates = [
        _candidate(title="Spatial Reasoning", source="arxiv", arxiv_id="arXiv:2401.12345v1"),
        _candidate(title="Spatial Reasoning in Robots", source="openalex", arxiv_id="2401.12345"),
    ]

    assert len(deduplicate(candidates)) == 1


def test_titles_differing_only_in_case_and_punctuation_merge() -> None:
    candidates = [
        _candidate(title="Embodied Spatial Intelligence: A Review"),
        _candidate(title="embodied spatial intelligence — a review", source="arxiv"),
    ]

    assert len(deduplicate(candidates)) == 1


def test_fuzzy_match_requires_author_overlap() -> None:
    reordered = [
        _candidate(title="Embodied Spatial Intelligence for Robots", authors=["Ada Lovelace"]),
        _candidate(
            title="Spatial Embodied Intelligence for Robots",
            source="arxiv",
            authors=["ada lovelace"],
        ),
    ]
    assert len(deduplicate(reordered)) == 1

    strangers = [
        _candidate(title="Embodied Spatial Intelligence for Robots", authors=["Ada Lovelace"]),
        _candidate(
            title="Spatial Embodied Intelligence for Robots",
            source="arxiv",
            authors=["Alan Turing"],
        ),
    ]
    assert len(deduplicate(strangers)) == 2


def test_distinct_papers_by_the_same_authors_stay_separate() -> None:
    candidates = [
        _candidate(title="Embodied Spatial Intelligence for Robots", authors=["Ada Lovelace"]),
        _candidate(title="A Survey of Protein Folding", source="arxiv", authors=["Ada Lovelace"]),
    ]

    assert len(deduplicate(candidates)) == 2


def test_merge_keeps_the_best_available_metadata() -> None:
    candidates = [
        _candidate(
            doi="10.1234/abcd",
            abstract="short",
            authors=["Ada Lovelace"],
            publication_date=date(2026, 9, 20),
            citation_count=3,
        ),
        _candidate(
            doi="10.1234/abcd",
            source="arxiv",
            source_id="2401.12345",
            abstract="a considerably longer abstract",
            authors=["Ada Lovelace", "Alan Turing"],
            publication_date=date(2026, 9, 10),
            citation_count=11,
            venue="NeurIPS",
            arxiv_id="2401.12345",
        ),
    ]

    merged = deduplicate(candidates)[0]

    assert merged.abstract == "a considerably longer abstract"
    assert merged.authors == ["Ada Lovelace", "Alan Turing"]
    assert merged.publication_date == date(2026, 9, 10)
    assert merged.citation_count == 11
    assert merged.venue == "NeurIPS"
    assert merged.arxiv_id == "2401.12345"


def test_candidates_without_identifiers_do_not_over_merge() -> None:
    candidates = [
        _candidate(title="Paper One"),
        _candidate(title="Paper Two", source="arxiv"),
        _candidate(title="Paper Three", source="semantic_scholar"),
    ]

    assert len(deduplicate(candidates)) == 3


def test_author_overlap_can_be_disabled() -> None:
    candidates = [
        _candidate(title="Embodied Spatial Intelligence for Robots", authors=["Ada Lovelace"]),
        _candidate(
            title="Spatial Embodied Intelligence for Robots",
            source="arxiv",
            authors=["Alan Turing"],
        ),
    ]
    settings = DeduplicationSettings(require_author_overlap=False)

    assert len(deduplicate(candidates, settings)) == 1


def test_output_is_deterministic_regardless_of_input_order() -> None:
    candidates = [
        _candidate(title="Paper One", doi="10.1234/one"),
        _candidate(title="Paper Two", source="arxiv", arxiv_id="2401.12345"),
        _candidate(title="Paper Three", source="semantic_scholar"),
        _candidate(title="Paper One", source="arxiv", doi="10.1234/one"),
    ]
    expected = [candidate.canonical_id for candidate in deduplicate(candidates)]

    shuffled = list(candidates)
    random.Random(7).shuffle(shuffled)

    assert [candidate.canonical_id for candidate in deduplicate(shuffled)] == expected
