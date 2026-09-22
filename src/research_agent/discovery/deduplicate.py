"""Deterministic deduplication of normalized paper candidates."""

from rapidfuzz import fuzz

from research_agent.config import DeduplicationSettings
from research_agent.discovery.normalize import normalize_candidate, normalize_title
from research_agent.domain.papers import PaperCandidate, SourceReference


def _sources_key(reference: SourceReference) -> tuple[str, str]:
    return reference.source, reference.source_id


def _longer(left: str | None, right: str | None) -> str | None:
    if left is None:
        return right
    if right is None:
        return left
    return left if len(left) >= len(right) else right


def merge(existing: PaperCandidate, incoming: PaperCandidate) -> PaperCandidate:
    """Combine two records of the same paper, keeping the best available metadata."""
    dates = [value for value in (existing.publication_date, incoming.publication_date) if value]
    counts = (existing.citation_count, incoming.citation_count)
    citations = [value for value in counts if value is not None]
    sources = {_sources_key(reference): reference for reference in existing.sources}
    for reference in incoming.sources:
        sources.setdefault(_sources_key(reference), reference)

    return existing.model_copy(
        update={
            "title": _longer(existing.title, incoming.title),
            "abstract": _longer(existing.abstract, incoming.abstract),
            "authors": max(existing.authors, incoming.authors, key=len),
            "publication_date": min(dates) if dates else None,
            "doi": existing.doi or incoming.doi,
            "arxiv_id": existing.arxiv_id or incoming.arxiv_id,
            "venue": existing.venue or incoming.venue,
            "citation_count": max(citations) if citations else None,
            "sources": [sources[key] for key in sorted(sources)],
            "discovered_at": min(existing.discovered_at, incoming.discovered_at),
        }
    )


def _shares_author(left: PaperCandidate, right: PaperCandidate) -> bool:
    return bool(
        {author.casefold() for author in left.authors}
        & {author.casefold() for author in right.authors}
    )


def deduplicate(
    candidates: list[PaperCandidate],
    settings: DeduplicationSettings | None = None,
) -> list[PaperCandidate]:
    """Collapse duplicate candidates in DOI, arXiv, exact-title, then fuzzy-title order."""
    settings = settings or DeduplicationSettings()
    accepted: list[PaperCandidate] = []
    by_doi: dict[str, int] = {}
    by_arxiv: dict[str, int] = {}
    by_title: dict[str, int] = {}

    for raw in candidates:
        candidate = normalize_candidate(raw)
        title_key = normalize_title(candidate.title)
        index = None
        if candidate.doi is not None:
            index = by_doi.get(candidate.doi)
        if index is None and candidate.arxiv_id is not None:
            index = by_arxiv.get(candidate.arxiv_id)
        if index is None:
            index = by_title.get(title_key)
        if index is None:
            # ponytail: O(n^2) fuzzy scan; fine within the 500-candidate limit. If that grows,
            # bucket accepted titles by a short prefix or token before comparing.
            for position, other in enumerate(accepted):
                score = fuzz.token_sort_ratio(title_key, normalize_title(other.title))
                if score < settings.title_similarity:
                    continue
                if settings.require_author_overlap and not _shares_author(candidate, other):
                    continue
                index = position
                break

        if index is None:
            accepted.append(candidate)
            index = len(accepted) - 1
        else:
            accepted[index] = merge(accepted[index], candidate)

        merged = accepted[index]
        if merged.doi is not None:
            by_doi[merged.doi] = index
        if merged.arxiv_id is not None:
            by_arxiv[merged.arxiv_id] = index
        by_title[title_key] = index
        by_title[normalize_title(merged.title)] = index

    return sorted(accepted, key=lambda candidate: candidate.canonical_id or "")
