"""Active and shadow execution (TRD section 14).

Only the active classifier controls routing. The shadow runs on the same papers, is persisted with
``is_active`` false, and can never fail or alter the primary run — that isolation lives here so no
call site has to remember it.
"""

import logging
from dataclasses import dataclass, field

from research_agent.classifiers.base import PaperClassifier, Provenance
from research_agent.config import TopicSettings
from research_agent.domain.analysis import ClassificationResult
from research_agent.domain.papers import PaperCandidate

_LOGGER = logging.getLogger(__name__)

Verdicts = list[tuple[ClassificationResult, Provenance]]


@dataclass(frozen=True)
class ClassifierOutcome:
    """What one classification pass produced; only ``active`` may influence a run."""

    active: Verdicts
    shadow: Verdicts = field(default_factory=list)
    shadow_error: str | None = None


class ClassifierRunner:
    """Run the active classifier, then the optional shadow one in a failure-proof wrapper."""

    def __init__(self, active: PaperClassifier, shadow: PaperClassifier | None = None) -> None:
        self._active = active
        self._shadow = shadow

    async def run(self, papers: list[PaperCandidate], topic: TopicSettings) -> ClassifierOutcome:
        active = await self._active.explain_many(papers, topic)
        if self._shadow is None:
            return ClassifierOutcome(active=active)

        try:
            shadow = await self._shadow.explain_many(papers, topic)
        # A shadow result is never worth failing a run, so every failure is caught here.
        except Exception as error:
            _LOGGER.warning(
                "shadow classifier failed; the run continues on the active result",
                extra={
                    "topic_id": topic.id,
                    "classifier": self._shadow.name,
                    "node_name": "classify",
                    "error_type": getattr(error, "category", "CLASSIFIER_ERROR"),
                    "status": "shadow_failed",
                },
            )
            return ClassifierOutcome(active=active, shadow_error=str(error))
        return ClassifierOutcome(active=active, shadow=shadow)
