"""Report generation: gather the run's records, optionally add prose, store atomically.

The report is the run's deliverable, so it is produced even when stages failed: a missing synthesis,
an abstract-only analysis or a dead provider each degrade one section rather than the document.
"""

import logging
from datetime import date

from pydantic import Field

from research_agent.config import ReportSettings, StrictModel, TopicSettings
from research_agent.domain.runs import RunRecord
from research_agent.models.base import ModelMessage, ModelProviderError
from research_agent.models.router import ModelRouter
from research_agent.reports.builder import ReportInputs, build_report
from research_agent.reports.naming import is_report, report_filename
from research_agent.reports.prompts import SYSTEM_PROMPT, ReportProse, render
from research_agent.storage.artifacts import ArtifactStore
from research_agent.storage.papers import PaperRepository
from research_agent.storage.results import ResultRepository
from research_agent.storage.runs import RunRepository

_LOGGER = logging.getLogger(__name__)


class ReportOutcome(StrictModel):
    """Where the report landed and whether it is a full or a degraded one."""

    path: str = Field(min_length=1)
    papers: int = Field(default=0, ge=0)
    empty_week: bool = False
    prose: bool = False
    """True when the executive summary was model-written rather than assembled."""

    degraded: bool = False


class ReportService:
    """Build one topic's weekly report from what the run actually persisted."""

    def __init__(
        self,
        store: ArtifactStore,
        results: ResultRepository,
        papers: PaperRepository,
        runs: RunRepository,
        router: ModelRouter | None = None,
        settings: ReportSettings | None = None,
    ) -> None:
        self._store = store
        self._results = results
        self._papers = papers
        self._runs = runs
        self._router = router
        self._settings = settings or ReportSettings()

    async def generate(
        self,
        topic: TopicSettings,
        run: RunRecord,
        paper_ids: list[str],
        period_start: date,
        period_end: date,
    ) -> ReportOutcome:
        """Assemble and store the report for one run, never raising."""
        analyses = [
            analysis
            for analysis in (self._results.analysis_for(paper_id) for paper_id in paper_ids)
            if analysis is not None
        ]
        papers = {
            paper_id: paper
            for paper_id in paper_ids
            if (paper := self._papers.get(paper_id)) is not None
        }
        history = self._results.recent_syntheses(topic.id, limit=1)
        inputs = ReportInputs(
            topic=topic,
            run=run,
            period_start=period_start,
            period_end=period_end,
            papers=papers,
            analyses=analyses,
            classifications=self._results.classifications_for(run.id),
            synthesis=history[0] if history else None,
            gaps=self._results.gaps_for(run.id),
            ideas=self._results.ideas_for(run.id),
            errors=self._runs.errors_for(run.id),
        )
        summary = await self._prose(inputs) if analyses else None
        markdown = build_report(inputs, summary)
        path = self._store.write_text(topic.id, "reports", report_filename(period_end), markdown)
        return ReportOutcome(
            path=str(path),
            papers=len(analyses),
            empty_week=not analyses,
            prose=summary is not None,
            degraded=bool(inputs.errors) or run.status in ("degraded", "failed"),
        )

    async def _prose(self, inputs: ReportInputs) -> str | None:
        """Ask for the executive summary; a failure costs a paragraph, not the report."""
        if self._router is None or not self._settings.include_prose:
            return None
        try:
            result = await self._router.generate(
                "report_writing",
                [
                    ModelMessage(role="system", content=SYSTEM_PROMPT),
                    ModelMessage(
                        role="user",
                        content=render(
                            inputs.topic,
                            inputs.synthesis,
                            len(inputs.analyses),
                            inputs.period_start.isoformat(),
                            inputs.period_end.isoformat(),
                            self._settings.max_input_chars,
                        ),
                    ),
                ],
                ReportProse,
            )
        except ModelProviderError as error:
            _LOGGER.warning(
                "report prose unavailable; the report is assembled without it",
                extra={
                    "topic_id": inputs.topic.id,
                    "node_name": "report",
                    "error_type": error.category,
                    "status": "degraded",
                },
            )
            return None
        prose = result.parsed
        return prose.executive_summary if isinstance(prose, ReportProse) else None

    def latest(self, topic_id: str) -> str | None:
        """The newest stored report for a topic, chosen by filename so the pick is deterministic."""
        names = [name for name in self._store.names(topic_id, "reports") if is_report(name)]
        if not names:
            return None
        return str(self._store.path_for(topic_id, "reports", names[-1]))
