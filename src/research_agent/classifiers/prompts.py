"""Versioned prompts for Classifier B.

A wording change is a new version string, so a persisted verdict always names the prompt that
produced it.
"""

from research_agent.config import TopicSettings
from research_agent.domain.papers import PaperCandidate

PROMPT_VERSION = "classification.v1"

SYSTEM_PROMPT = (
    "You triage academic papers for one research topic. Reply with JSON only, in the form "
    '{"relevance": "high|medium|low", "relevance_score": 0.0, '
    '"paper_type": "method|dataset|benchmark|survey|application|other", '
    '"action": "ignore|summarize|deep_read", "confidence": 0.0, "reason_short": "..."}. '
    "Scores are between 0 and 1. Choose deep_read only for papers central to the topic, "
    "summarize for related work, and ignore for the rest. Keep reason_short under 20 words."
)

REPAIR_INSTRUCTION = (
    "That reply was not valid JSON in the required shape. Reply again with the JSON object only, "
    "no prose, no code fences, and no fields beyond the ones listed."
)

_TEMPLATE = """Topic: {name}
Topic keywords: {keywords}

Paper title: {title}
Paper abstract: {abstract}"""

_TRUNCATED = " [abstract truncated]"


def render(paper: PaperCandidate, topic: TopicSettings, max_abstract_chars: int) -> str:
    """Render the user prompt, bounding the abstract so it cannot overrun a local context window."""
    return _TEMPLATE.format(
        name=topic.name,
        keywords=", ".join(topic.keywords) if topic.keywords else "none",
        title=paper.title,
        abstract=_abstract(paper.abstract, max_abstract_chars),
    )


def _abstract(abstract: str | None, max_abstract_chars: int) -> str:
    if not abstract:
        return "none available; judge from the title alone"
    if len(abstract) <= max_abstract_chars:
        return abstract
    # Saying so keeps the model from reading a cut sentence as the paper's conclusion.
    return abstract[:max_abstract_chars] + _TRUNCATED
