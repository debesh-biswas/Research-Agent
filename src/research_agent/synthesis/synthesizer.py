"""Synthesis orchestration: history retrieval, reference validation, and provenance.

The model may only produce a :class:`SynthesisDraft`. Which papers existed, which period this was,
and which model wrote it are supplied here, and any finding citing a paper outside the run's corpus
is corrected or dropped before anything is persisted.
"""

import logging
from datetime import date

from pydantic import Field

from research_agent.config import StrictModel, SynthesisSettings, TopicSettings
from research_agent.domain.analysis import (
    PaperAnalysis,
    SupportedFinding,
    SynthesisDraft,
    WeeklySynthesis,
)
from research_agent.models.base import ModelMessage, ModelProviderError
from research_agent.models.router import ModelRouter
from research_agent.storage.results import ResultRepository
from research_agent.synthesis.prompts import PROMPT_VERSION, SYSTEM_PROMPT, render

_LOGGER = logging.getLogger(__name__)

_EVIDENCE_FIELDS = (
    "major_developments",
    "emerging_directions",
    "methods_gaining_attention",
    "contradictions",
    "common_limitations",
)


class SynthesisOutcome(StrictModel):
    """Either a stored synthesis or the reason there is none; a failure never ends the run."""

    synthesis: WeeklySynthesis | None = None
    dropped_findings: int = Field(default=0, ge=0)
    """Findings removed because they cited no paper in this run's corpus."""

    reason: str | None = None


class WeeklySynthesizer:
    """Compare a run's analyses with each other and with the topic's recent history."""

    def __init__(
        self,
        router: ModelRouter,
        results: ResultRepository,
        settings: SynthesisSettings | None = None,
    ) -> None:
        self._router = router
        self._results = results
        self._settings = settings or SynthesisSettings()

    async def synthesize(
        self,
        topic: TopicSettings,
        run_id: str,
        analyses: list[PaperAnalysis],
        titles: dict[str, str],
        period_start: date,
        period_end: date,
    ) -> SynthesisOutcome:
        """Produce and persist one synthesis, never raising, whatever the provider does."""
        if not analyses:
            return SynthesisOutcome(reason="no analyses to synthesize")

        history = self._results.recent_syntheses(topic.id, self._settings.history_window)
        messages = [
            ModelMessage(role="system", content=SYSTEM_PROMPT),
            ModelMessage(
                role="user",
                content=render(
                    topic,
                    analyses,
                    titles,
                    history,
                    period_start.isoformat(),
                    period_end.isoformat(),
                    self._settings.max_input_chars,
                ),
            ),
        ]
        try:
            result = await self._router.generate("synthesis", messages, SynthesisDraft)
        except ModelProviderError as error:
            _LOGGER.warning(
                "weekly synthesis failed",
                extra={
                    "topic_id": topic.id,
                    "node_name": "synthesize",
                    "error_type": error.category,
                    "status": "failed",
                },
            )
            return SynthesisOutcome(reason=str(error))

        draft = result.parsed
        if not isinstance(draft, SynthesisDraft):
            return SynthesisOutcome(reason="no validated synthesis was returned")

        known = {analysis.paper_id for analysis in analyses}
        supported, dropped = _supported(draft, known)
        synthesis = WeeklySynthesis(
            **supported.model_dump(),
            paper_ids=sorted(known),
            model_provider=result.provider,
            model_name=result.model,
            prompt_version=PROMPT_VERSION,
            history_periods=len(history),
        )
        self._results.save_synthesis(run_id, topic.id, synthesis, period_start, period_end)
        return SynthesisOutcome(synthesis=synthesis, dropped_findings=dropped)


def _supported(draft: SynthesisDraft, known: set[str]) -> tuple[SynthesisDraft, int]:
    """Keep only findings that cite this run's papers, with their references in stable order."""
    updates: dict[str, list[SupportedFinding]] = {}
    dropped = 0
    for field in _EVIDENCE_FIELDS:
        kept: list[SupportedFinding] = []
        for finding in getattr(draft, field):
            references = sorted({ref for ref in finding.supporting_paper_ids if ref in known})
            if not references:
                dropped += 1
                continue
            kept.append(finding.model_copy(update={"supporting_paper_ids": references}))
        updates[field] = kept
    return draft.model_copy(update=updates), dropped
