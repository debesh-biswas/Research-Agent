"""The classifier contract every triage implementation shares (TRD section 10).

The protocol is async because Classifier B (F9) must await the model router and Classifier A
awaits optional embeddings; the TRD's synchronous sketch cannot express either.
"""

from typing import Protocol

from research_agent.config import TopicSettings
from research_agent.domain.analysis import ClassificationResult
from research_agent.domain.papers import PaperCandidate
from research_agent.domain.runs import ErrorCategory


class ClassifierError(Exception):
    """A classifier could not produce a verdict; the category feeds the run error taxonomy."""

    def __init__(self, message: str, category: ErrorCategory = "CLASSIFIER_ERROR") -> None:
        super().__init__(message)
        self.category: ErrorCategory = category


class PaperClassifier(Protocol):
    """One triage implementation, independent of how it reaches its decision."""

    @property
    def name(self) -> str: ...

    async def classify(
        self, paper: PaperCandidate, topic: TopicSettings
    ) -> ClassificationResult: ...

    async def classify_many(
        self, papers: list[PaperCandidate], topic: TopicSettings
    ) -> list[ClassificationResult]: ...
