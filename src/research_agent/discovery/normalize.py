"""Deterministic metadata normalization for discovered papers.

Every function here is pure so the workflow can normalize candidates without touching the
network, the clock, or the filesystem.
"""

import hashlib
import re
import unicodedata
from datetime import date, datetime

from research_agent.domain.papers import PaperCandidate, SourceReference

_WHITESPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/")
_DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$")
_ARXIV_MODERN = re.compile(r"^\d{4}\.\d{4,5}$")
_ARXIV_LEGACY = re.compile(r"^[a-z-]+(\.[a-z]{2})?/\d{7}$")
_ARXIV_VERSION = re.compile(r"v\d+$")
_UNSAFE_ID = re.compile(r"[^a-z0-9]+")


def normalize_text(value: str | None) -> str | None:
    """Apply NFKC normalization, collapse whitespace, and drop empty results."""
    if value is None:
        return None
    normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip()
    return normalized or None


def normalize_title(value: str) -> str:
    """Return a title reduced to a comparison key; punctuation and case are discarded."""
    normalized = normalize_text(value) or ""
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", normalized)).strip().casefold()


def normalize_doi(value: str | None) -> str | None:
    """Return a bare `10.x/y` DOI, or None when the value is not a DOI."""
    candidate = normalize_text(value)
    if candidate is None:
        return None
    candidate = candidate.replace(" ", "").lower()
    for prefix in _DOI_PREFIXES:
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :]
            break
    else:
        if candidate.startswith("doi:"):
            candidate = candidate[4:]
    return candidate if _DOI_PATTERN.match(candidate) else None


def normalize_arxiv_id(value: str | None) -> str | None:
    """Return a version-stripped arXiv identifier, or None when the value is not one."""
    candidate = normalize_text(value)
    if candidate is None:
        return None
    candidate = candidate.replace(" ", "").lower()
    if candidate.startswith("arxiv:"):
        candidate = candidate[6:]
    candidate = _ARXIV_VERSION.sub("", candidate)
    if _ARXIV_MODERN.match(candidate) or _ARXIV_LEGACY.match(candidate):
        return candidate
    return None


def normalize_author(value: str | None) -> str | None:
    """Normalize a single author name for display and comparison."""
    return normalize_text(value)


def normalize_authors(values: list[str]) -> list[str]:
    """Normalize author names, dropping blanks and duplicates while preserving order."""
    seen: set[str] = set()
    authors: list[str] = []
    for value in values:
        author = normalize_author(value)
        if author is None or author.casefold() in seen:
            continue
        seen.add(author.casefold())
        authors.append(author)
    return authors


def normalize_url(value: str | None) -> str | None:
    """Keep only http(s) URLs; anything else is treated as missing."""
    candidate = normalize_text(value)
    if candidate is None:
        return None
    return candidate if candidate.lower().startswith(("http://", "https://")) else None


def normalize_date(value: date | datetime | str | None) -> date | None:
    """Accept dates, datetimes, and YYYY / YYYY-MM / ISO-8601 strings; return a date or None."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    candidate = normalize_text(value)
    if candidate is None:
        return None
    # Accept partial dates by filling in the missing month and day.
    for attempt in (candidate, f"{candidate}-01", f"{candidate}-01-01"):
        try:
            return datetime.fromisoformat(attempt).date()
        except ValueError:
            continue
    return None


def canonical_id(candidate: PaperCandidate) -> str:
    """Build a stable, filename-safe identifier: DOI, else arXiv ID, else a title hash."""
    if candidate.doi is not None:
        return f"doi_{_UNSAFE_ID.sub('_', candidate.doi).strip('_')}"
    if candidate.arxiv_id is not None:
        return f"arxiv_{_UNSAFE_ID.sub('_', candidate.arxiv_id).strip('_')}"
    first_author = candidate.authors[0].casefold() if candidate.authors else ""
    digest = hashlib.sha256(f"{normalize_title(candidate.title)}|{first_author}".encode())
    return f"title_{digest.hexdigest()[:12]}"


def content_hash(candidate: PaperCandidate) -> str:
    """Hash the text an analysis actually reads, so a revised paper stops matching its old one."""
    title = normalize_title(candidate.title)
    abstract = normalize_text(candidate.abstract) or ""
    return hashlib.sha256(f"{title}|{abstract}".encode()).hexdigest()


def _normalize_source(reference: SourceReference) -> SourceReference:
    return reference.model_copy(
        update={
            "url": normalize_url(reference.url),
            "pdf_url": normalize_url(reference.pdf_url),
        }
    )


def normalize_candidate(candidate: PaperCandidate) -> PaperCandidate:
    """Return a copy with every field normalized and `canonical_id` assigned."""
    normalized = candidate.model_copy(
        update={
            "title": normalize_text(candidate.title) or candidate.title,
            "abstract": normalize_text(candidate.abstract),
            "authors": normalize_authors(candidate.authors),
            "publication_date": normalize_date(candidate.publication_date),
            "doi": normalize_doi(candidate.doi),
            "arxiv_id": normalize_arxiv_id(candidate.arxiv_id),
            "venue": normalize_text(candidate.venue),
            "sources": [_normalize_source(reference) for reference in candidate.sources],
        }
    )
    return normalized.model_copy(update={"canonical_id": canonical_id(normalized)})
