"""Breadth reaches both prompts: what is searched for, and how widely screening accepts."""

from datetime import UTC, datetime

import pytest

from research_agent.config import Breadth, ScreeningSettings, TopicSettings
from research_agent.domain.papers import PaperCandidate, SourceReference
from research_agent.queries import prompts as query_prompts
from research_agent.screening import prompts as screening_prompts
from research_agent.topics.breadth import QUERY_GUIDANCE, SCREENING_GUIDANCE

PAPER = PaperCandidate(
    title="Language-Conditioned Topological Maps",
    abstract="Named maps.",
    discovered_at=datetime(2026, 10, 1, tzinfo=UTC),
    sources=[SourceReference(source="arxiv", source_id="1")],
)


@pytest.mark.parametrize("breadth", ["focused", "balanced", "exploratory"])
def test_each_breadth_has_its_own_wording_in_both_prompts(breadth: Breadth) -> None:
    topic = TopicSettings(id="t", name="Embodied Spatial", description="Robots and maps.")
    topic = topic.model_copy(update={"breadth": breadth})

    screening = screening_prompts.render(PAPER, topic, ScreeningSettings())
    queries = query_prompts.render(topic.name, [], [], 5, 20, topic.description, topic.breadth)

    assert SCREENING_GUIDANCE[breadth] in screening
    assert QUERY_GUIDANCE[breadth] in queries
    assert "What it covers: Robots and maps." in screening and "Robots and maps." in queries
    others = set(SCREENING_GUIDANCE) - {breadth}
    assert not any(SCREENING_GUIDANCE[other] in screening for other in others)


def test_a_topic_without_keywords_or_description_says_so_plainly() -> None:
    topic = TopicSettings(id="t", name="Embodied Spatial")

    screening = screening_prompts.render(PAPER, topic, ScreeningSettings())
    queries = query_prompts.render(topic.name, [], [], 5, 20)

    assert "Topic keywords" not in screening and "What it covers" not in screening
    assert "infer it from the name" in queries
    assert "Extra terms the reader asked for: none" in queries


def test_keywords_from_the_cli_still_reach_both_prompts() -> None:
    topic = TopicSettings(id="t", name="Embodied Spatial", keywords=["scene graphs"])

    assert "Topic keywords: scene graphs" in screening_prompts.render(
        PAPER, topic, ScreeningSettings()
    )
    assert "scene graphs" in query_prompts.render(topic.name, topic.keywords, [], 5, 20)
