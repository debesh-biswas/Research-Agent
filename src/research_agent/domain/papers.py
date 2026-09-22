"""Provider-neutral paper candidate schema."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from research_agent.config import StrictModel

SourceName = Literal["openalex", "semantic_scholar", "arxiv"]


class SourceReference(StrictModel):
    """One provider's record of a paper, retained for provenance after merging."""

    source: SourceName
    source_id: str = Field(min_length=1)
    url: str | None = None
    pdf_url: str | None = None


class PaperCandidate(StrictModel):
    """A discovered paper before classification, independent of the source it came from."""

    canonical_id: str | None = None
    title: str = Field(min_length=1)
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    publication_date: date | None = None
    discovered_at: datetime
    sources: list[SourceReference] = Field(min_length=1)
    doi: str | None = None
    arxiv_id: str | None = None
    venue: str | None = None
    citation_count: int | None = Field(default=None, ge=0)
