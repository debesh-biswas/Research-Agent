"""Analysis orchestration: caching, provenance, and failure isolation around one model call.

The model only ever supplies an :class:`AnalysisDraft`. Everything a reader has to be able to trust
— which paper it describes, which model wrote it, whether it read the full text, and whether a
claim's citation is real — is filled in here from the run's own facts.
"""

import asyncio
import logging
from typing import Literal

from pydantic import Field

from research_agent.analysis.cards import render_card
from research_agent.analysis.prompts import PROMPT_VERSION, render, system_prompt
from research_agent.config import AnalysisSettings, StrictModel, TopicSettings
from research_agent.discovery.normalize import canonical_id
from research_agent.domain.analysis import AnalysisDraft, Claim, PaperAnalysis
from research_agent.domain.documents import ParsedPaper
from research_agent.domain.papers import PaperCandidate
from research_agent.models.base import ModelMessage, ModelProviderError
from research_agent.models.router import ModelRouter
from research_agent.storage.artifacts import ArtifactStore
from research_agent.storage.papers import PaperRepository
from research_agent.storage.results import ResultRepository

_LOGGER = logging.getLogger(__name__)

AnalysisStatus = Literal["analyzed", "cached", "failed"]


class AnalysisOutcome(StrictModel):
    """What analysis did with one paper; a failure never ends the run."""

    paper_id: str = Field(min_length=1)
    status: AnalysisStatus
    abstract_only: bool = False
    path: str | None = None
    reason: str | None = None


class PaperAnalyzer:
    """Turn selected papers into validated analyses and Markdown paper cards."""

    def __init__(
        self,
        router: ModelRouter,
        results: ResultRepository,
        papers: PaperRepository,
        store: ArtifactStore,
        settings: AnalysisSettings | None = None,
        concurrency: int = 2,
    ) -> None:
        self._router = router
        self._results = results
        self._papers = papers
        self._store = store
        self._settings = settings or AnalysisSettings()
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    async def analyze_many(
        self,
        papers: list[PaperCandidate],
        parsed: dict[str, ParsedPaper],
        topic: TopicSettings,
        run_id: str,
        force: bool = False,
    ) -> list[AnalysisOutcome]:
        """Analyse a batch under bounded concurrency; one failing paper never loses the others."""
        outcomes = await asyncio.gather(
            *(self._bounded(paper, parsed, topic, run_id, force) for paper in papers),
            return_exceptions=True,
        )
        results: list[AnalysisOutcome] = []
        for paper, outcome in zip(papers, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                # Only a defect reaches here; provider and validation failures are outcomes below.
                results.append(
                    AnalysisOutcome(
                        paper_id=_identifier(paper), status="failed", reason=str(outcome)
                    )
                )
                continue
            results.append(outcome)
        return results

    async def _bounded(
        self,
        paper: PaperCandidate,
        parsed: dict[str, ParsedPaper],
        topic: TopicSettings,
        run_id: str,
        force: bool,
    ) -> AnalysisOutcome:
        async with self._semaphore:
            return await self.analyze(paper, parsed.get(_identifier(paper)), topic, run_id, force)

    async def analyze(
        self,
        paper: PaperCandidate,
        parsed: ParsedPaper | None,
        topic: TopicSettings,
        run_id: str,
        force: bool = False,
    ) -> AnalysisOutcome:
        """Analyse one paper, reusing a stored analysis unless forced, and never raising."""
        paper_id = _identifier(paper)
        if not force and self._results.analysis_for(paper_id) is not None:
            return AnalysisOutcome(paper_id=paper_id, status="cached")

        messages = [
            ModelMessage(role="system", content=system_prompt(self._settings.include_claims)),
            ModelMessage(
                role="user", content=render(paper, parsed, topic, self._settings.max_input_chars)
            ),
        ]
        try:
            result = await self._router.generate("deep_reasoning", messages, AnalysisDraft)
        except ModelProviderError as error:
            _LOGGER.warning(
                "paper analysis failed",
                extra={
                    "topic_id": topic.id,
                    "paper_id": paper_id,
                    "node_name": "analyze",
                    "error_type": error.category,
                    "status": "failed",
                },
            )
            return AnalysisOutcome(paper_id=paper_id, status="failed", reason=str(error))

        draft = result.parsed
        if not isinstance(draft, AnalysisDraft):
            return AnalysisOutcome(
                paper_id=paper_id, status="failed", reason="no validated analysis was returned"
            )

        abstract_only = parsed is None or not parsed.text.strip()
        analysis = PaperAnalysis(
            paper_id=paper_id,
            model_provider=result.provider,
            model_name=result.model,
            prompt_version=PROMPT_VERSION,
            abstract_only=abstract_only,
            **draft.model_dump(exclude={"key_claims"}),
            key_claims=[] if not self._settings.include_claims else _grounded(draft, parsed),
        )
        self._results.save_analysis(run_id, analysis)
        self._papers.mark_analyzed(paper_id)
        path = self._store.write_text(
            topic.id, "analyses", f"{paper_id}.md", render_card(analysis, paper)
        )
        return AnalysisOutcome(
            paper_id=paper_id, status="analyzed", abstract_only=abstract_only, path=str(path)
        )


def _identifier(paper: PaperCandidate) -> str:
    return paper.canonical_id or canonical_id(paper)


def _grounded(draft: AnalysisDraft, parsed: ParsedPaper | None) -> list[Claim]:
    """Drop provenance a claim cannot support, rather than persist a fabricated citation.

    TRD section 28 makes page and section provenance best-effort, so a claim survives without it.
    """
    sections = (
        {section.title for section in parsed.sections if section.title} if parsed else set[str]()
    )
    grounded: list[Claim] = []
    for claim in draft.key_claims:
        if claim.source_section is not None and claim.source_section not in sections:
            claim = claim.model_copy(update={"source_section": None, "page": None})
        grounded.append(claim)
    return grounded
