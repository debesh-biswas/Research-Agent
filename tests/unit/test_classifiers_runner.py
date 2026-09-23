import asyncio

import pytest
from conftest import candidate

from research_agent.classifiers.base import ClassifierError, PaperClassifier, Provenance
from research_agent.classifiers.runner import ClassifierRunner
from research_agent.config import TopicSettings
from research_agent.domain.analysis import ClassificationResult
from research_agent.domain.papers import PaperCandidate

TOPIC = TopicSettings.model_validate({"id": "spatial_intelligence", "name": "Spatial Intelligence"})
PAPERS = [candidate()]


class FakeClassifier:
    """A classifier that answers with one fixed action, or fails."""

    def __init__(
        self, name: str, action: str = "deep_read", error: Exception | None = None
    ) -> None:
        self.name = name
        self._action = action
        self._error = error
        self.calls = 0

    async def classify(self, paper: PaperCandidate, topic: TopicSettings) -> ClassificationResult:
        results = await self.explain_many([paper], topic)
        return results[0][0]

    async def classify_many(
        self, papers: list[PaperCandidate], topic: TopicSettings
    ) -> list[ClassificationResult]:
        return [result for result, _ in await self.explain_many(papers, topic)]

    async def explain_many(
        self, papers: list[PaperCandidate], topic: TopicSettings
    ) -> list[tuple[ClassificationResult, Provenance]]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return [
            (
                ClassificationResult(
                    paper_id=paper.canonical_id or "paper",
                    classifier_name=self.name,
                    relevance="high",
                    paper_type="method",
                    action=self._action,  # type: ignore[arg-type]
                ),
                {"version": "fake.v1"},
            )
            for paper in papers
        ]


def _protocol_check(classifier: PaperClassifier) -> str:
    return classifier.name


def test_a_fake_classifier_satisfies_the_protocol() -> None:
    assert _protocol_check(FakeClassifier("classifier_a")) == "classifier_a"


def test_without_a_shadow_only_the_active_classifier_runs() -> None:
    active = FakeClassifier("classifier_a")

    outcome = asyncio.run(ClassifierRunner(active).run(PAPERS, TOPIC))

    assert [result.classifier_name for result, _ in outcome.active] == ["classifier_a"]
    assert (outcome.shadow, outcome.shadow_error) == ([], None)
    assert active.calls == 1


def test_a_shadow_result_is_returned_separately_and_never_mixed_in() -> None:
    outcome = asyncio.run(
        ClassifierRunner(
            FakeClassifier("classifier_a", action="summarize"),
            FakeClassifier("classifier_b", action="ignore"),
        ).run(PAPERS, TOPIC)
    )

    assert [result.action for result, _ in outcome.active] == ["summarize"]
    assert [result.action for result, _ in outcome.shadow] == ["ignore"]


def test_a_failing_shadow_classifier_cannot_fail_the_run() -> None:
    outcome = asyncio.run(
        ClassifierRunner(
            FakeClassifier("classifier_a"),
            FakeClassifier("classifier_b", error=ClassifierError("model is down")),
        ).run(PAPERS, TOPIC)
    )

    assert len(outcome.active) == 1
    assert outcome.shadow == []
    assert outcome.shadow_error is not None and "model is down" in outcome.shadow_error


def test_a_failing_active_classifier_does_fail_the_run() -> None:
    runner = ClassifierRunner(
        FakeClassifier("classifier_a", error=ClassifierError("model is down")),
        FakeClassifier("classifier_b"),
    )

    with pytest.raises(ClassifierError):
        asyncio.run(runner.run(PAPERS, TOPIC))
