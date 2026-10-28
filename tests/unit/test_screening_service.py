import sqlite3
from datetime import UTC, datetime

import pytest

from research_agent.config import ApplicationSettings, TopicSettings
from research_agent.discovery.normalize import canonical_id
from research_agent.domain.analysis import ClassificationResult, ClassifierVerdict
from research_agent.domain.feedback import FeedbackExamples
from research_agent.domain.papers import PaperCandidate, SourceReference
from research_agent.models.base import ModelProviderError, ModelResult
from research_agent.screening.service import PaperScreener
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from tests.unit.conftest import TOPIC_ID, candidate


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


class CountingRouter(Router):
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *args: object, **kwargs: object) -> ModelResult:
        self.calls += 1
        return await super().generate(*args, **kwargs)


@pytest.mark.anyio
async def test_an_identical_prompt_reuses_the_stored_verdict(
    connection: sqlite3.Connection,
) -> None:
    results = SqliteResultRepository(connection)
    run = SqliteRunRepository(connection).start(TOPIC_ID)
    paper = candidate(abstract="Named topological maps for household robots.")
    SqlitePaperRepository(connection).upsert(paper)
    router = CountingRouter()
    topic = TopicSettings(id=TOPIC_ID, name="Spatial Intelligence", keywords=["maps"])

    async def screen(
        screener: PaperScreener, topic: TopicSettings, examples: FeedbackExamples | None = None
    ) -> dict[str, object]:
        outcome, failures = await screener.screen_many([paper], topic, examples)
        assert failures == []
        result, provenance = outcome[0]
        key = provenance["prompt_key"]
        assert isinstance(key, str)
        results.save_classification(run.id, result, raw_response=provenance, prompt_key=key)
        return provenance

    screener = PaperScreener(router, ApplicationSettings(), cache=results)  # type: ignore[arg-type]
    first = await screen(screener, topic)
    again = await screen(screener, topic)
    assert router.calls == 1
    assert "reused" not in first and again["reused"] is True
    assert again["prompt_key"] == first["prompt_key"]
    assert results.classifications_for(run.id)[1].action == "ignore"

    await screen(screener, topic.model_copy(update={"keywords": ["maps", "graphs"]}))
    assert router.calls == 2, "new keywords ask again"
    await screen(screener, topic, FeedbackExamples(relevant=["A map paper"], not_relevant=[]))
    assert router.calls == 3, "new votes ask again"
    other_model = ApplicationSettings.model_validate({"models": {"local": {"model": "other"}}})
    await screen(PaperScreener(router, other_model, cache=results), topic)  # type: ignore[arg-type]
    assert router.calls == 4, "a different model asks again"


def test_only_an_active_verdict_with_that_exact_key_is_reused(
    connection: sqlite3.Connection,
) -> None:
    results = SqliteResultRepository(connection)
    run = SqliteRunRepository(connection).start(TOPIC_ID)
    paper = candidate()
    SqlitePaperRepository(connection).upsert(paper)
    verdict = ClassificationResult(
        paper_id=canonical_id(paper),
        classifier_name="semantic_screening",
        relevance="high",
        relevance_score=0.9,
        paper_type="method",
        action="deep_read",
        confidence=0.9,
        reason_short="On topic.",
    )
    results.save_classification(run.id, verdict, is_active=False, prompt_key="k")
    assert results.screening_for("k") is None
    results.save_classification(run.id, verdict)
    assert results.screening_for("k") is None, "rows saved without a key never match"
    results.save_classification(run.id, verdict, prompt_key="k")
    assert results.screening_for("k") == verdict
