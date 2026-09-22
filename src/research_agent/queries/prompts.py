"""Versioned prompts for query expansion.

A wording change is a new version string, so a persisted plan always names the prompt that produced
it.
"""

from research_agent.domain.analysis import WeeklySynthesis

PROMPT_VERSION = "query_expansion.v1"

SYSTEM_PROMPT = (
    "You expand a research topic into academic search queries. "
    'Reply with JSON only, in the form {"queries": ["..."]}. '
    "Each query is a short phrase of search terms, not a sentence or a question. "
    "Cover distinct sub-areas, methods, datasets, and applications rather than rephrasing one idea."
)

_TEMPLATE = """Topic: {name}
Known keywords: {keywords}
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
) -> str:
    """Render the user prompt; absent keywords or history degrade to an explicit 'none'."""
    return _TEMPLATE.format(
        name=name,
        keywords=", ".join(keywords) if keywords else "none",
        history=_history(history),
        min_queries=min_queries,
        max_queries=max_queries,
    )


def _history(history: list[WeeklySynthesis]) -> str:
    """Flatten previous syntheses into bullets, so the model expands into what is already moving."""
    bullets = [
        f"- {item}"
        for synthesis in history
        for item in (*synthesis.major_developments, *synthesis.emerging_directions)
    ]
    return "\n".join(bullets) if bullets else "- none recorded yet"
