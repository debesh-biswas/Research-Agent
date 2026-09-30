"""Ask the local model for candidate keywords before a new topic is created."""

import logging

from pydantic import Field

from research_agent.config import StrictModel
from research_agent.models.base import ModelMessage, ModelProviderError
from research_agent.models.router import ModelRouter
from research_agent.topics import prompts

_LOGGER = logging.getLogger(__name__)


class KeywordSuggestion(StrictModel):
    """The model's proposed keywords for a topic; never empty and never absurdly long."""

    keywords: list[str] = Field(min_length=1, max_length=10)


async def suggest_keywords(router: ModelRouter, name: str, description: str) -> list[str]:
    """Suggest keywords for a topic; unavailable inference degrades to an empty list."""
    messages = [
        ModelMessage(role="system", content=prompts.SYSTEM_PROMPT),
        ModelMessage(role="user", content=prompts.render(name, description)),
    ]
    try:
        result = await router.generate(
            "cheap_text", messages, KeywordSuggestion, task="topic_keywords"
        )
    except ModelProviderError:
        _LOGGER.warning(
            "keyword suggestion unavailable; the topic can still be created without them",
            extra={"node_name": "topic_keywords", "status": "fallback"},
        )
        return []
    suggestion = result.parsed
    return suggestion.keywords if isinstance(suggestion, KeywordSuggestion) else []
