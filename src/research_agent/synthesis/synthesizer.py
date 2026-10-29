"""Synthesis orchestration: history retrieval, reference validation, and provenance.

The model may only produce a :class:`SynthesisDraft`. Which papers existed, which period this was,
and which model wrote it are supplied here, and any finding citing a paper outside the run's corpus
is corrected or dropped before anything is persisted.
"""

import asyncio
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
from research_agent.models.base import Capability, ModelMessage, ModelProviderError, ModelResult
from research_agent.models.router import ModelRouter
from research_agent.storage.results import ResultRepository
from research_agent.synthesis.prompts import (
    MERGE_SYSTEM_PROMPT,
    MERGED_ENTRIES,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    batches,
    render,
    render_merge,
)

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
    batches: int = Field(default=1, ge=1)
    """How many batch calls the week took; 1 when it fit in one prompt."""


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
        start, end = period_start.isoformat(), period_end.isoformat()
        budget = self._settings.max_input_chars
        groups = batches(topic, analyses, titles, history, start, end, budget)
        if len(groups) == 1:
            prompt = render(topic, analyses, titles, history, start, end, budget)
            outcome = await self._draft(topic, SYSTEM_PROMPT, prompt, "synthesize")
            if isinstance(outcome, str):
                return SynthesisOutcome(reason=outcome)
            draft, result = outcome
        else:
            # A big week no longer loses everything past the budget: each batch fits, with room
            # for the model to reason, and one more call merges the batches into the week.
            partials = await asyncio.gather(
                *(
                    self._draft(
                        topic,
                        SYSTEM_PROMPT,
                        render(topic, group, titles, history, start, end, budget, batched=True),
                        "synthesize_batch",
                    )
                    for group in groups
                )
            )
            drafted = [item for item in partials if not isinstance(item, str)]
            if not drafted:
                return SynthesisOutcome(reason=f"every batch failed: {partials[0]}")
            merged = await self._draft(
                topic,
                MERGE_SYSTEM_PROMPT,
                render_merge(topic, [d for d, _ in drafted], history, start, end, budget),
                "synthesize_merge",
                "synthesis_merge",
            )
            if isinstance(merged, str):
                # Batch findings are still evidence-backed; a plain union beats no synthesis.
                draft, result = _union([d for d, _ in drafted]), drafted[0][1]
            else:
                draft, result = merged

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
        return SynthesisOutcome(
            synthesis=synthesis,
            dropped_findings=dropped,
            batches=len(groups),
        )

    async def _draft(
        self,
        topic: TopicSettings,
        system: str,
        prompt: str,
        step: str,
        capability: Capability = "synthesis",
    ) -> tuple[SynthesisDraft, ModelResult] | str:
        """One synthesis call: the validated draft and its result, or why there is none."""
        messages = [
            ModelMessage(role="system", content=system),
            ModelMessage(role="user", content=prompt),
        ]
        try:
            result = await self._router.generate(capability, messages, SynthesisDraft, task=step)
        except ModelProviderError as error:
            _LOGGER.warning(
                "weekly synthesis failed: %s",
                error,
                extra={
                    "topic_id": topic.id,
                    "node_name": step,
                    "error_type": error.category,
                    "status": "failed",
                },
            )
            return str(error)
        draft = result.parsed
        if not isinstance(draft, SynthesisDraft):
            return "no validated synthesis was returned"
        return draft, result


def _union(drafts: list[SynthesisDraft]) -> SynthesisDraft:
    """The batches' findings taken in turn (each batch's best first), repeats removed.

    Evidence fields stop at the merge's own cap, so a fallback report stays as readable as a
    merged one; dataset and benchmark names are kept in full.
    """
    fields: dict[str, list[object]] = {}
    for field in SynthesisDraft.model_fields:
        columns = [list(getattr(draft, field)) for draft in drafts]
        interleaved = [
            value
            for rank in range(max((len(column) for column in columns), default=0))
            for column in columns
            if rank < len(column)
            for value in [column[rank]]
        ]
        seen: set[str] = set()
        values: list[object] = []
        for value in interleaved:
            key = value.text if isinstance(value, SupportedFinding) else str(value)
            if key not in seen:
                seen.add(key)
                values.append(value)
        capped = field in _EVIDENCE_FIELDS
        fields[field] = values[:MERGED_ENTRIES] if capped else values
    return SynthesisDraft.model_validate(fields)


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
