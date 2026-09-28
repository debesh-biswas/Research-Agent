"""Deterministic paper-quality signals used to order already relevant papers."""

from datetime import date
from math import log1p

from research_agent.config import SelectionSettings
from research_agent.discovery.normalize import normalize_title
from research_agent.domain.papers import PaperCandidate


def paper_quality_score(
    paper: PaperCandidate,
    settings: SelectionSettings,
    as_of: date,
) -> float:
    """Return a bounded quality score from recency, venue, citations, and source metadata.

    This is a ranking signal, not a claim that an unreviewed paper is poor. Missing metadata gets
    a neutral-low score so it cannot outrank a recent paper in a known respected venue by accident.
    """
    recency = _recency_score(paper.publication_date, as_of, settings.recency_window_days)
    venue = _venue_score(paper.venue, settings.preferred_venues)
    citations = _citation_score(paper.citation_count)
    source = _source_score(paper)
    return round(0.45 * recency + 0.35 * venue + 0.15 * citations + 0.05 * source, 4)


def ranking_score(
    relevance_score: float | None,
    paper: PaperCandidate | None,
    settings: SelectionSettings,
    as_of: date,
) -> float:
    """Blend classifier relevance with quality while keeping relevance as the eligibility gate."""
    relevance = relevance_score or 0.0
    quality = 0.0 if paper is None else paper_quality_score(paper, settings, as_of)
    return round((1 - settings.quality_weight) * relevance + settings.quality_weight * quality, 4)


def _recency_score(publication_date: date | None, as_of: date, window_days: int) -> float:
    if publication_date is None:
        return 0.2
    age = max(0, (as_of - publication_date).days)
    return max(0.0, 1.0 - age / window_days)


def _venue_score(venue: str | None, preferred_venues: list[str]) -> float:
    if not venue:
        return 0.2
    normalized = normalize_title(venue)
    preferred = [normalize_title(value) for value in preferred_venues if normalize_title(value)]
    if any(value in normalized for value in preferred):
        return 1.0
    return 0.55


def _citation_score(citation_count: int | None) -> float:
    if citation_count is None:
        return 0.2
    return min(1.0, log1p(citation_count) / log1p(100))


def _source_score(paper: PaperCandidate) -> float:
    sources = {reference.source for reference in paper.sources}
    if "semantic_scholar" in sources or "openalex" in sources:
        return 0.75
    return 0.35
