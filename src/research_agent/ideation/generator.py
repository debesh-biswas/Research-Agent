"""Ideation orchestration: two bounded model calls, reference validation, and deduplication.

Gaps come from the week's synthesis; ideas come from the surviving gaps. Both are checked against
the run's own paper ids, because an untraceable gap or idea is generic brainstorming, which the PRD
explicitly does not want.
"""

import logging

from pydantic import BaseModel, Field

from research_agent.config import IdeationSettings, StrictModel, TopicSettings
from research_agent.discovery.normalize import normalize_title
from research_agent.domain.analysis import (
    GapDraft,
    IdeaDraft,
    ResearchGap,
    ResearchIdea,
    WeeklySynthesis,
)
from research_agent.ideation.prompts import (
    GAP_PROMPT_VERSION,
    IDEA_PROMPT_VERSION,
    gap_system_prompt,
    idea_system_prompt,
    render_gaps,
    render_ideas,
)
from research_agent.models.base import ModelMessage, ModelProviderError, ModelResult
from research_agent.models.router import ModelRouter
from research_agent.storage.results import ResultRepository

_LOGGER = logging.getLogger(__name__)


class GapsReply(StrictModel):
    """The gap call's envelope; a list at the top level is not valid JSON object output."""

    gaps: list[GapDraft] = Field(default_factory=list)


class IdeasReply(StrictModel):
    ideas: list[IdeaDraft] = Field(default_factory=list)


class IdeationOutcome(StrictModel):
    """What ideation produced, plus what it refused to keep."""

    gaps: list[ResearchGap] = Field(default_factory=list)
    ideas: list[ResearchIdea] = Field(default_factory=list)
    dropped_gaps: int = Field(default=0, ge=0)
    dropped_ideas: int = Field(default=0, ge=0)
    reason: str | None = None


class IdeationService:
    """Derive research gaps and then ideas from one stored synthesis, never raising."""

    def __init__(
        self,
        router: ModelRouter,
        results: ResultRepository,
        settings: IdeationSettings | None = None,
    ) -> None:
        self._router = router
        self._results = results
        self._settings = settings or IdeationSettings()

    async def generate(
        self, topic: TopicSettings, run_id: str, synthesis: WeeklySynthesis
    ) -> IdeationOutcome:
        """Produce gaps and ideas for one run and persist both, or report why there are none."""
        known = set(synthesis.paper_ids)
        try:
            gap_result = await self._call(
                gap_system_prompt(self._settings.max_gaps),
                render_gaps(topic, synthesis, self._settings.max_input_chars),
                GapsReply,
            )
        except ModelProviderError as error:
            return self._failed("gap detection", topic, error)

        gaps, dropped_gaps = _gaps(gap_result, known, self._settings.max_gaps)
        if not gaps:
            return IdeationOutcome(
                dropped_gaps=dropped_gaps, reason="no gap was supported by a paper in this run"
            )
        self._results.save_gaps(run_id, topic.id, gaps)

        try:
            idea_result = await self._call(
                idea_system_prompt(self._settings.max_ideas),
                render_ideas(topic, gaps, sorted(known), self._settings.max_input_chars),
                IdeasReply,
            )
        except ModelProviderError as error:
            outcome = self._failed("ideation", topic, error)
            return outcome.model_copy(update={"gaps": gaps, "dropped_gaps": dropped_gaps})

        titles = {gap.title for gap in gaps}
        ideas, dropped_ideas = _ideas(idea_result, known, titles, self._settings.max_ideas)
        if ideas:
            self._results.save_ideas(run_id, topic.id, ideas)
        return IdeationOutcome(
            gaps=gaps,
            ideas=ideas,
            dropped_gaps=dropped_gaps,
            dropped_ideas=dropped_ideas,
        )

    async def _call(self, system: str, user: str, schema: type[BaseModel]) -> ModelResult:
        return await self._router.generate(
            "ideation",
            [
                ModelMessage(role="system", content=system),
                ModelMessage(role="user", content=user),
            ],
            schema,
        )

    def _failed(
        self, stage: str, topic: TopicSettings, error: ModelProviderError
    ) -> IdeationOutcome:
        _LOGGER.warning(
            "ideation failed",
            extra={
                "topic_id": topic.id,
                "node_name": "ideate",
                "error_type": error.category,
                "status": "failed",
            },
        )
        return IdeationOutcome(reason=f"{stage} failed: {error}")


def _gaps(result: ModelResult, known: set[str], limit: int) -> tuple[list[ResearchGap], int]:
    reply = result.parsed
    if not isinstance(reply, GapsReply):
        return [], 0
    kept: list[ResearchGap] = []
    dropped = 0
    for draft in reply.gaps:
        references = _references(draft.supporting_paper_ids, known)
        if not references or len(kept) >= limit:
            dropped += 1
            continue
        kept.append(
            ResearchGap(
                **draft.model_dump(exclude={"supporting_paper_ids"}),
                supporting_paper_ids=references,
                model_provider=result.provider,
                model_name=result.model,
                prompt_version=GAP_PROMPT_VERSION,
            )
        )
    return kept, dropped


def _ideas(
    result: ModelResult, known: set[str], gap_titles: set[str], limit: int
) -> tuple[list[ResearchIdea], int]:
    reply = result.parsed
    if not isinstance(reply, IdeasReply):
        return [], 0
    kept: list[ResearchIdea] = []
    seen: set[str] = set()
    dropped = 0
    for draft in reply.ideas:
        references = _references(draft.supporting_paper_ids, known)
        fingerprint = normalize_title(draft.title)
        unsupported = not references or draft.identified_gap not in gap_titles
        if unsupported or fingerprint in seen or len(kept) >= limit:
            dropped += 1
            continue
        seen.add(fingerprint)
        kept.append(
            ResearchIdea(
                **draft.model_dump(exclude={"supporting_paper_ids"}),
                supporting_paper_ids=references,
                model_provider=result.provider,
                model_name=result.model,
                prompt_version=IDEA_PROMPT_VERSION,
            )
        )
    return kept, dropped


def _references(candidates: list[str], known: set[str]) -> list[str]:
    """Keep only real papers, deduplicated and ordered, so stored references are deterministic."""
    return sorted({reference for reference in candidates if reference in known})
