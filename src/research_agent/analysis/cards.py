"""The per-paper Markdown card (PRD section 12).

Deterministic layout and field order, so the same analysis always renders identically. Every value
originates in a model reply or a provider payload, so all of it is treated as untrusted text.
"""

from research_agent.domain.analysis import Claim, PaperAnalysis
from research_agent.domain.papers import PaperCandidate
from research_agent.utils.markdown import block as _block
from research_agent.utils.markdown import inline as _inline

_ABSTRACT_ONLY_NOTE = (
    "> Abstract-only analysis: no parsed full text was available, so depth is limited."
)


def render_card(analysis: PaperAnalysis, paper: PaperCandidate) -> str:
    """Render one paper card, omitting sections the analysis has nothing to say about."""
    lines = [f"# {_inline(paper.title)}", ""]
    lines.extend(_metadata(analysis, paper))
    if analysis.abstract_only:
        lines.extend(["", _ABSTRACT_ONLY_NOTE])
    lines.extend(_prose("Research problem", analysis.research_problem))
    lines.extend(_prose("Main contribution", analysis.main_contribution))
    lines.extend(_prose("Method", analysis.method))
    lines.extend(_prose("Experimental setup", analysis.experimental_setup))
    lines.extend(_bullets("Datasets", analysis.datasets))
    lines.extend(_bullets("Benchmarks", analysis.benchmarks))
    lines.extend(_bullets("Main results", analysis.main_results))
    lines.extend(_bullets("Strengths", analysis.strengths))
    lines.extend(_bullets("Limitations", analysis.limitations))
    lines.extend(_claims(analysis.key_claims))
    lines.extend(_bullets("Related work", analysis.related_work))
    lines.extend(_prose("Topic relevance", analysis.topic_relevance))
    return "\n".join(lines).rstrip() + "\n"


def _metadata(analysis: PaperAnalysis, paper: PaperCandidate) -> list[str]:
    fields = [
        ("Paper", analysis.paper_id),
        ("Authors", ", ".join(paper.authors) if paper.authors else None),
        ("Date", paper.publication_date.isoformat() if paper.publication_date else None),
        ("Venue", paper.venue),
        ("DOI", paper.doi),
        ("arXiv", paper.arxiv_id),
        ("Model", f"{analysis.model_provider}/{analysis.model_name}"),
        ("Prompt", analysis.prompt_version),
    ]
    return [f"- **{label}:** {_inline(value)}" for label, value in fields if value]


def _prose(heading: str, value: str | None) -> list[str]:
    if not value or not value.strip():
        return []
    return ["", f"## {heading}", "", _block(value)]


def _bullets(heading: str, values: list[str]) -> list[str]:
    items = [value for value in values if value and value.strip()]
    if not items:
        return []
    return ["", f"## {heading}", "", *(f"- {_inline(item)}" for item in items)]


def _claims(claims: list[Claim]) -> list[str]:
    if not claims:
        return []
    lines = ["", "## Key claims", ""]
    for claim in claims:
        provenance = [
            part
            for part in (
                f"section: {_inline(claim.source_section)}" if claim.source_section else None,
                f"page {claim.page}" if claim.page else None,
            )
            if part
        ]
        suffix = f" ({'; '.join(provenance)})" if provenance else " (provenance unavailable)"
        lines.append(f"- {_inline(claim.text)}{suffix}")
        if claim.evidence_excerpt:
            lines.append(f'  - evidence: "{_inline(claim.evidence_excerpt)}"')
    return lines
