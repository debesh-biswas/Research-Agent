"""Classifier B: the small-LLM triage path (PRD 7.2, TRD section 12).

It reaches a model only through :class:`ModelRouter`, so it never names a provider or an endpoint.
Malformed structured output is repaired exactly once, which is the ceiling the TRD sets.
"""

import asyncio
import logging

from research_agent.classifiers.base import ClassifierError
from research_agent.classifiers.prompts import (
    PROMPT_VERSION,
    REPAIR_INSTRUCTION,
    SYSTEM_PROMPT,
    render,
)
from research_agent.config import ClassifierBSettings, TopicSettings
from research_agent.discovery.normalize import canonical_id
from research_agent.domain.analysis import ClassificationResult, ClassifierVerdict
from research_agent.domain.papers import PaperCandidate
from research_agent.models.base import (
    ModelMessage,
    ModelProviderError,
    ModelResult,
    ModelValidationError,
)
from research_agent.models.router import ModelRouter

_LOGGER = logging.getLogger(__name__)

Provenance = dict[str, object]


class ClassifierB:
    """Classify papers with the configured local LLM, validating every reply against a schema."""

    name = "classifier_b"

    def __init__(
        self,
        router: ModelRouter,
        settings: ClassifierBSettings | None = None,
        concurrency: int = 2,
    ) -> None:
        self._router = router
        self._settings = settings or ClassifierBSettings()
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    async def classify(self, paper: PaperCandidate, topic: TopicSettings) -> ClassificationResult:
        result, _ = await self._one(paper, topic)
        return result

    async def classify_many(
        self, papers: list[PaperCandidate], topic: TopicSettings
    ) -> list[ClassificationResult]:
        return [result for result, _ in await self.explain_many(papers, topic)]

    async def explain_many(
        self, papers: list[PaperCandidate], topic: TopicSettings
    ) -> list[tuple[ClassificationResult, Provenance]]:
        """Classify a batch with bounded concurrency; one failing paper never loses the others."""
        outcomes = await asyncio.gather(
            *(self._bounded(paper, topic) for paper in papers), return_exceptions=True
        )
        verdicts: list[tuple[ClassificationResult, Provenance]] = []
        for paper, outcome in zip(papers, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                _LOGGER.warning(
                    "classification failed; the paper is skipped",
                    extra={
                        "topic_id": topic.id,
                        "paper_id": paper.canonical_id or canonical_id(paper),
                        "node_name": "classify",
                        "error_type": getattr(outcome, "category", "CLASSIFIER_ERROR"),
                        "status": "skipped",
                    },
                )
                continue
            verdicts.append(outcome)
        return verdicts

    async def _bounded(
        self, paper: PaperCandidate, topic: TopicSettings
    ) -> tuple[ClassificationResult, Provenance]:
        async with self._semaphore:
            return await self._one(paper, topic)

    async def _one(
        self, paper: PaperCandidate, topic: TopicSettings
    ) -> tuple[ClassificationResult, Provenance]:
        messages = [
            ModelMessage(role="system", content=SYSTEM_PROMPT),
            ModelMessage(
                role="user", content=render(paper, topic, self._settings.max_abstract_chars)
            ),
        ]
        repaired = False
        try:
            result = await self._generate(messages)
        except ModelValidationError as error:
            # The single repair retry the TRD allows; the router deliberately does not retry these.
            repaired = True
            messages.append(ModelMessage(role="user", content=REPAIR_INSTRUCTION))
            try:
                result = await self._generate(messages)
            except ModelValidationError as repair_error:
                raise ClassifierError(
                    f"{self.name} returned invalid output twice: {repair_error}",
                    "INVALID_CLASSIFIER_OUTPUT",
                ) from error
        except ModelProviderError as error:
            raise ClassifierError(f"{self.name} inference failed: {error}", error.category) from (
                error
            )

        verdict = result.parsed
        if not isinstance(verdict, ClassifierVerdict):
            raise ClassifierError(
                f"{self.name} returned no validated verdict", "INVALID_CLASSIFIER_OUTPUT"
            )
        return self._result(paper, verdict, result, repaired)

    async def _generate(self, messages: list[ModelMessage]) -> ModelResult:
        return await self._router.generate(
            "classification", messages, ClassifierVerdict, task="classification"
        )

    def _result(
        self,
        paper: PaperCandidate,
        verdict: ClassifierVerdict,
        result: ModelResult,
        repaired: bool,
    ) -> tuple[ClassificationResult, Provenance]:
        classification = ClassificationResult(
            paper_id=paper.canonical_id or canonical_id(paper),
            classifier_name=self.name,
            latency_ms=result.latency_ms,
            **verdict.model_dump(),
        )
        provenance: Provenance = {
            "version": PROMPT_VERSION,
            "model_provider": result.provider,
            "model_name": result.model,
            "fell_back": result.fell_back,
            "repaired": repaired,
        }
        return classification, provenance
