"""Versioned prompt for single-paper analysis.

A wording change is a new version string, so every persisted analysis names the prompt that
produced it.
"""

from research_agent.config import TopicSettings
from research_agent.domain.documents import ParsedPaper
from research_agent.domain.papers import PaperCandidate

PROMPT_VERSION = "paper_analysis.v1"

SYSTEM_PROMPT = (
    "You analyse one academic paper for a research topic. Reply with JSON only, in the form "
    '{"research_problem": "...", "main_contribution": "...", "method": "...", '
    '"datasets": ["..."], "benchmarks": ["..."], "experimental_setup": "...", '
    '"main_results": ["..."], "strengths": ["..."], "limitations": ["..."], '
    '"key_claims": [{"text": "...", "source_section": "...", "page": 1, '
    '"evidence_excerpt": "..."}], "related_work": ["..."], "topic_relevance": "..."}. '
    "Use only what the provided text supports; never invent a result, a dataset, or a citation. "
    "For each key claim name the section it came from exactly as that section is headed, and quote "
    "a short excerpt. Omit source_section, page, and evidence_excerpt when you cannot ground them. "
    "Add no fields beyond the ones listed."
)

_NO_CLAIMS = "Return key_claims as an empty list."

_TEMPLATE = """Topic: {name}
Topic keywords: {keywords}

Paper title: {title}
Paper authors: {authors}

{body_label}:
{body}"""

_TRUNCATED = "\n\n[text truncated; the paper continues beyond this point]"


def render(
    paper: PaperCandidate,
    parsed: ParsedPaper | None,
    topic: TopicSettings,
    max_input_chars: int,
) -> str:
    """Render the user prompt from parsed full text when there is any, else the abstract alone."""
    if parsed is not None and parsed.text.strip():
        body_label, body = "Paper full text", parsed.text
    else:
        body_label = "Paper abstract (no parsed full text is available)"
        body = paper.abstract or "none available; analyse from the title alone and say so"
    return _TEMPLATE.format(
        name=topic.name,
        keywords=", ".join(topic.keywords) if topic.keywords else "none",
        title=paper.title,
        authors=", ".join(paper.authors) if paper.authors else "unknown",
        body_label=body_label,
        body=_bounded(body, max_input_chars),
    )


def system_prompt(include_claims: bool) -> str:
    """The system prompt, minus the claim work when a topic does not want claims."""
    return SYSTEM_PROMPT if include_claims else f"{SYSTEM_PROMPT} {_NO_CLAIMS}"


def _bounded(body: str, max_input_chars: int) -> str:
    if len(body) <= max_input_chars:
        return body
    # Saying so keeps the model from reading a cut sentence as the paper's conclusion.
    return body[:max_input_chars] + _TRUNCATED
