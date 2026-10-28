"""Versioned prompts for query expansion.

A wording change is a new version string, so a persisted plan always names the prompt that produced
it.
"""

from research_agent.config import Breadth
from research_agent.domain.analysis import WeeklySynthesis
from research_agent.topics.breadth import QUERY_GUIDANCE

PROMPT_VERSION = "query_expansion.v2"
"""v2 adds the topic's description and breadth; the model chooses the terms itself."""

SYSTEM_PROMPT = (
    "You expand a research topic into academic search queries. "
    'Reply with JSON only, in the form {"queries": ["..."]}. '
    "Each query is a short phrase of search terms, not a sentence or a question. "
    "Cover distinct sub-areas, methods, datasets, and applications rather than rephrasing one idea."
)

_TEMPLATE = """Topic: {name}
What it covers: {description}
{guidance}
Extra terms the reader asked for: {keywords}
Recent developments in this topic:
{history}

Return between {min_queries} and {max_queries} search queries for papers
published in the last few weeks."""


def render(
    name: str,
    keywords: list[str],
    history: list[WeeklySynthesis],
    min_queries: int,
    max_queries: int,
    description: str = "",
    breadth: Breadth = "balanced",
) -> str:
    """Render the user prompt; absent keywords or history degrade to an explicit 'none'."""
    return _TEMPLATE.format(
        name=name,
        description=description.strip() or "not described; infer it from the name",
        guidance=QUERY_GUIDANCE[breadth],
        keywords=", ".join(keywords) if keywords else "none",
        history=_history(history),
        min_queries=min_queries,
        max_queries=max_queries,
    )


def _history(history: list[WeeklySynthesis]) -> str:
    """Flatten previous syntheses into bullets, so the model expands into what is already moving."""
    bullets = [
        f"- {finding.text}"
        for synthesis in history
        for finding in (*synthesis.major_developments, *synthesis.emerging_directions)
    ]
    return "\n".join(bullets) if bullets else "- none recorded yet"
