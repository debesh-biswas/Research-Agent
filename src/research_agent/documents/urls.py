"""Which URLs a paper's PDF may legally be fetched from.

Pure and deterministic. Only open-access locations the sources themselves reported, plus arXiv's
public PDF endpoint, ever appear here: no publisher-page scraping and no paywall probing.
"""

from urllib.parse import urlsplit, urlunsplit

from research_agent.domain.papers import PaperCandidate, SourceName

_ARXIV_PDF = "https://arxiv.org/pdf/{arxiv_id}"
# A fixed order, so two runs over the same paper request the same URL first.
_SOURCE_ORDER: tuple[SourceName, ...] = ("openalex", "semantic_scholar", "arxiv")


def pdf_candidates(paper: PaperCandidate) -> list[str]:
    """Ordered, deduplicated PDF URLs to try; an empty list means the paper is unavailable."""
    candidates: list[str] = []
    if paper.arxiv_id:
        candidates.append(_ARXIV_PDF.format(arxiv_id=paper.arxiv_id))
    for source in _SOURCE_ORDER:
        for reference in paper.sources:
            if reference.source == source and reference.pdf_url:
                candidates.append(reference.pdf_url)

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        secure = _https(candidate)
        if secure is not None and secure not in seen:
            seen.add(secure)
            ordered.append(secure)
    return ordered


def _https(url: str) -> str | None:
    """Upgrade http to https and reject every other scheme; nothing else is fetchable."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return urlunsplit(parts._replace(scheme="https"))
