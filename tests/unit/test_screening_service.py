from datetime import UTC, datetime

import pytest

from research_agent.config import ApplicationSettings, TopicSettings
from research_agent.domain.analysis import ClassifierVerdict
from research_agent.domain.feedback import FeedbackExamples
from research_agent.domain.papers import PaperCandidate, SourceReference
from research_agent.models.base import ModelProviderError, ModelResult
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

    screener = PaperScreener(Router(), ApplicationSettings())  # type: ignore[arg-type]
    results, failures = await screener.screen_many([paper], topic)

    assert len(results) == 1
    assert failures == []
    assert results[0][0].action == "ignore"
    assert results[0][0].relevance_score == 0.05


class DeadRouter:
    async def generate(self, *args: object, **kwargs: object) -> ModelResult:
        raise ModelProviderError("upstream is unwell", "MODEL_API_ERROR")


@pytest.mark.anyio
async def test_a_dead_provider_is_reported_as_a_screening_failure() -> None:
    """A screening failure must surface with its category so the run status reflects it."""
    paper = PaperCandidate(
        title="Bandwidth, Latency, and 400 Million Kilometers",
        abstract="A Mars compute paper that mentions computer vision as one possible workload.",
        authors=[],
        discovered_at=datetime.now(UTC),
        sources=[SourceReference(source="openalex", source_id="1")],
    )
    topic = TopicSettings(id="computer_vision", name="Computer Vision")

    screener = PaperScreener(DeadRouter(), ApplicationSettings())  # type: ignore[arg-type]
    results, failures = await screener.screen_many([paper], topic)

    assert results == []
    assert len(failures) == 1
    assert failures[0].category == "MODEL_API_ERROR"
    assert failures[0].paper_id


class RecordingRouter(Router):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate(self, *args: object, **kwargs: object) -> ModelResult:
        messages = args[1]
        assert isinstance(messages, list)
        self.prompts.append(messages[-1].content)
        return await super().generate(*args, **kwargs)


def _paper() -> PaperCandidate:
    return PaperCandidate(
        title="Topological Maps for Home Robots",
        abstract="A named map.",
        authors=[],
        discovered_at=datetime.now(UTC),
        sources=[SourceReference(source="arxiv", source_id="1")],
    )


@pytest.mark.anyio
async def test_feedback_votes_reach_the_screening_prompt_only_when_present() -> None:
    topic = TopicSettings(id="spatial", name="Spatial Intelligence")
    router = RecordingRouter()
    screener = PaperScreener(router, ApplicationSettings())  # type: ignore[arg-type]
    examples = FeedbackExamples(relevant=["Semantic SLAM in Kitchens"], not_relevant=["CTR " * 80])

    plain, _ = await screener.screen_many([_paper()], topic)
    guided, _ = await screener.screen_many([_paper()], topic, examples)
    await screener.screen_many([_paper()], topic, FeedbackExamples())

    without, with_votes, with_none = router.prompts
    assert "Marked relevant" not in without and without == with_none
    assert "- Marked relevant: Semantic SLAM in Kitchens" in with_votes
    assert "- Marked not relevant: " + ("CTR " * 80)[:200] + "\n" in with_votes
    assert (plain[0][1]["feedback_examples"], guided[0][1]["feedback_examples"]) == (0, 2)
    assert guided[0][1]["version"] == "screening.v2"
