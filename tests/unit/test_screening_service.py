from datetime import UTC, datetime

import pytest

from research_agent.config import ApplicationSettings, TopicSettings
from research_agent.domain.analysis import ClassifierVerdict
from research_agent.domain.papers import PaperCandidate, SourceReference
from research_agent.models.base import ModelResult
from research_agent.screening.service import PaperScreener


class Router:
    async def generate(self, *args: object, **kwargs: object) -> ModelResult:
        return ModelResult(
            provider="nvidia_nim",
            model="test-model",
            text="{}",
            parsed=ClassifierVerdict(
                relevance="low",
                relevance_score=0.05,
                paper_type="other",
                action="ignore",
                confidence=0.95,
                reason_short="Computer vision is only an incidental example.",
            ),
        )


@pytest.mark.anyio
async def test_incidental_topic_mention_is_persisted_as_not_relevant() -> None:
    paper = PaperCandidate(
        title="Bandwidth, Latency, and 400 Million Kilometers",
        abstract="A Mars compute paper that mentions computer vision as one possible workload.",
        authors=[],
        discovered_at=datetime.now(UTC),
        sources=[SourceReference(source="openalex", source_id="1")],
    )
    topic = TopicSettings(id="computer_vision", name="Computer Vision")

    results = await PaperScreener(Router(), ApplicationSettings()).screen_many([paper], topic)  # type: ignore[arg-type]

    assert len(results) == 1
    assert results[0][0].action == "ignore"
    assert results[0][0].relevance_score == 0.05
