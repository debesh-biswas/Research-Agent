"""Versioned prompts for the single semantic screening path."""

from research_agent.config import ScreeningSettings, TopicSettings
from research_agent.domain.feedback import FeedbackExamples
from research_agent.domain.papers import PaperCandidate
from research_agent.topics.breadth import SCREENING_GUIDANCE

PROMPT_VERSION = "screening.v3"
"""v2 added the reader's relevance votes; v3 adds the topic's description and breadth."""

_EXAMPLE_TITLE_CHARS = 200
SYSTEM_PROMPT = """You are a careful research-paper screener. Judge whether the paper's central
contribution is relevant to the configured research topic. Do not mark a paper relevant merely
because it incidentally mentions a topic term. Return exactly one JSON object with these fields:
relevance (high|medium|low), relevance_score (number 0 to 1), paper_type
(method|dataset|benchmark|survey|application|other), action (ignore|summarize|deep_read),
confidence (number 0 to 1), reason_short (string). Do not include Markdown, commentary, or other
keys."""
REPAIR_INSTRUCTION = (
    "Your previous response was invalid. Return exactly the required JSON object, with every field "
    "and no Markdown."
)


def render(
    paper: PaperCandidate,
    topic: TopicSettings,
    settings: ScreeningSettings,
    examples: FeedbackExamples | None = None,
) -> str:
    abstract = (paper.abstract or "No abstract available.")[: settings.max_abstract_chars]
    described = (
        f"What it covers: {topic.description.strip()}\n" if topic.description.strip() else ""
    )
    terms = f"Topic keywords: {', '.join(topic.keywords)}\n" if topic.keywords else ""
    return f"""Topic: {topic.name}
{described}{terms}{SCREENING_GUIDANCE[topic.breadth]}
{_examples(examples)}Paper title: {paper.title}
Paper abstract: {abstract}

Return relevance, relevance_score, paper_type, action, confidence, and reason_short. Use ignore
unless the paper's main contribution belongs to the topic. Use summarize for relevant papers and
deep_read only for highly relevant, substantive advances."""


def _examples(examples: FeedbackExamples | None) -> str:
    """The reader's votes as guidance, or nothing at all when there are none."""
    if examples is None or not (examples.relevant or examples.not_relevant):
        return ""
    lines = ["The researcher's own judgements for this topic, as guidance (not a keyword list):"]
    for label, titles in (
        ("Marked relevant", examples.relevant),
        ("Marked not relevant", examples.not_relevant),
    ):
        lines.extend(f"- {label}: {title[:_EXAMPLE_TITLE_CHARS]}" for title in titles)
    return "\n".join(lines) + "\nJudge the paper below on its own content.\n"
