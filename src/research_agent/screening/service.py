"""One semantic paper screener backed by NIM with local fallback."""

import asyncio
import logging

from pydantic import Field

from research_agent.config import ApplicationSettings, StrictModel, TopicSettings
from research_agent.discovery.normalize import canonical_id
from research_agent.domain.analysis import ClassificationResult, ClassifierVerdict
from research_agent.domain.papers import PaperCandidate
from research_agent.domain.runs import ErrorCategory
from research_agent.models.base import ModelMessage, ModelProviderError, ModelValidationError
from research_agent.models.router import ModelRouter
from research_agent.screening.prompts import (
    PROMPT_VERSION,
    REPAIR_INSTRUCTION,
    SYSTEM_PROMPT,
    render,
)

_LOGGER = logging.getLogger(__name__)
Provenance = dict[str, object]


class ScreeningError(Exception):
    def __init__(self, message: str, category: ErrorCategory = "CLASSIFIER_ERROR") -> None:
        super().__init__(message)
        self.category = category


class ScreeningFailure(StrictModel):
    """A paper that screening could not resolve, so the run stays observably degraded."""

    paper_id: str = Field(min_length=1)
    category: ErrorCategory
    reason: str


class PaperScreener:
    """Screen candidates semantically; malformed output gets one repair before local fallback."""

    name = "semantic_screening"

    def __init__(self, router: ModelRouter, settings: ApplicationSettings) -> None:
        self._router = router
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.concurrency.analysis)

    async def screen_many(
        self, papers: list[PaperCandidate], topic: TopicSettings
    ) -> tuple[list[tuple[ClassificationResult, Provenance]], list[ScreeningFailure]]:
        outcomes = await asyncio.gather(
            *(self._one_bounded(paper, topic) for paper in papers), return_exceptions=True
        )
        accepted: list[tuple[ClassificationResult, Provenance]] = []
        failed: list[ScreeningFailure] = []
        for paper, outcome in zip(papers, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                category: ErrorCategory = getattr(outcome, "category", "CLASSIFIER_ERROR")
                _LOGGER.warning(
                    "screening failed; paper remains unresolved",
                    extra={"paper_id": canonical_id(paper), "error_type": category},
                )
                failed.append(
                    ScreeningFailure(
                        paper_id=canonical_id(paper), category=category, reason=str(outcome)
                    )
                )
                continue
            accepted.append(outcome)
        return accepted, failed

    async def _one_bounded(
        self, paper: PaperCandidate, topic: TopicSettings
    ) -> tuple[ClassificationResult, Provenance]:
        async with self._semaphore:
            messages = [
                ModelMessage(role="system", content=SYSTEM_PROMPT),
                ModelMessage(role="user", content=render(paper, topic, self._settings.screening)),
            ]
            repaired = False
            try:
                result = await self._router.generate(
                    "screening", messages, ClassifierVerdict, task="screening"
                )
            except ModelValidationError as error:
                repaired = True
                messages.append(ModelMessage(role="user", content=REPAIR_INSTRUCTION))
                try:
                    result = await self._router.generate(
                        "screening", messages, ClassifierVerdict, task="screening"
                    )
                except ModelValidationError:
                    try:
                        result = await self._router.generate_local(
                            "screening", messages, ClassifierVerdict, task="screening"
                        )
                    except (ModelValidationError, ModelProviderError) as final:
                        raise ScreeningError(
                            f"screening failed after repair and fallback: {final}",
                            "INVALID_CLASSIFIER_OUTPUT",
                        ) from error
            except ModelProviderError as error:
                raise ScreeningError(str(error), error.category) from error
            verdict = result.parsed
            if not isinstance(verdict, ClassifierVerdict):
                raise ScreeningError(
                    "screening produced no validated result", "INVALID_CLASSIFIER_OUTPUT"
                )
            record = ClassificationResult(
                paper_id=canonical_id(paper),
                classifier_name=self.name,
                latency_ms=result.latency_ms,
                **verdict.model_dump(),
            )
            return record, {
                "version": PROMPT_VERSION,
                "model_provider": result.provider,
                "model_name": result.model,
                "fell_back": result.fell_back,
                "repaired": repaired,
            }
