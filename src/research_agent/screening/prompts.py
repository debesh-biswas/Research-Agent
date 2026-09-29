"""Versioned prompts for the single semantic screening path."""

from research_agent.config import ScreeningSettings, TopicSettings
from research_agent.domain.papers import PaperCandidate

PROMPT_VERSION = "screening.v1"
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


def render(paper: PaperCandidate, topic: TopicSettings, settings: ScreeningSettings) -> str:
    abstract = (paper.abstract or "No abstract available.")[: settings.max_abstract_chars]
    return f"""Topic: {topic.name}
Topic keywords: {", ".join(topic.keywords) or "none supplied"}
Paper title: {paper.title}
Paper abstract: {abstract}

Return relevance, relevance_score, paper_type, action, confidence, and reason_short. Use ignore
unless the paper's main contribution belongs to the topic. Use summarize for relevant papers and
deep_read only for highly relevant, substantive advances."""
