"""Turn stored runs into the JSON shelf the reading desk already renders.

The shape matches ``web/js/data.js``. A week with no synthesis still appears, so a degraded
run is visible instead of disappearing from the desk.
"""

from datetime import date, datetime

from research_agent.config import TopicSettings
from research_agent.domain.analysis import (
    ClassificationResult,
    PaperAnalysis,
    ResearchGap,
    ResearchIdea,
    SupportedFinding,
    WeeklySynthesis,
)
from research_agent.domain.papers import PaperCandidate
from research_agent.domain.runs import ErrorRecord, RunRecord, RunSummary
from research_agent.domain.selection import SelectionDecision
from research_agent.reports.naming import report_filename
from research_agent.storage.artifacts import ArtifactKind, ArtifactStore
from research_agent.storage.feedback import FeedbackRepository
from research_agent.storage.papers import PaperRepository
from research_agent.storage.reading import ReadingRepository, ReadingState
from research_agent.storage.results import ResultRepository
from research_agent.storage.runs import RunRepository
from research_agent.storage.selections import SelectionRepository

_RUN_LIMIT = 12


def build_shelf(
    topics: list[TopicSettings],
    runs: RunRepository,
    results: ResultRepository,
    papers: PaperRepository,
    selections: SelectionRepository,
    store: ArtifactStore,
    *,
    reading: ReadingRepository | None = None,
    feedback: FeedbackRepository | None = None,
    run_limit: int = _RUN_LIMIT,
) -> dict[str, object]:
    """One JSON document for every configured topic and its recent runs."""
    return {
        "live": True,
        # What a new topic starts from, so the page never keeps its own copy of the defaults.
        "defaults": TopicSettings(id="new", name="New").model_dump(
            mode="json", exclude={"id", "name"}
        ),
        "topics": [
            {
                "id": topic.id,
                "name": topic.name,
                "settings": topic.model_dump(mode="json"),
                "runs": [
                    _run(topic, record, runs, results, papers, selections, store, reading, feedback)
                    for record in runs.recent(topic.id, run_limit)
                ],
            }
            for topic in topics
        ],
    }


def build_run(
    topic: TopicSettings,
    record: RunRecord,
    runs: RunRepository,
    results: ResultRepository,
    papers: PaperRepository,
    selections: SelectionRepository,
    store: ArtifactStore,
    *,
    reading: ReadingRepository | None = None,
    feedback: FeedbackRepository | None = None,
) -> dict[str, object]:
    """One run in the shelf's shape, for a run older than the shelf's recent window."""
    return _run(topic, record, runs, results, papers, selections, store, reading, feedback)


def find_run(shelf: dict[str, object], topic_id: str, run_id: str) -> dict[str, object] | None:
    """The run object inside a shelf, or none when the ids are not on it."""
    topics = shelf.get("topics")
    if not isinstance(topics, list):
        return None
    for topic in topics:
        if not isinstance(topic, dict) or topic.get("id") != topic_id:
            continue
        runs = topic.get("runs")
        if not isinstance(runs, list):
            continue
        for run in runs:
            if isinstance(run, dict) and run.get("id") == run_id:
                return run
    return None


def executive_summary_text(markdown: str) -> str | None:
    """The prose under the report's executive-summary heading, without the degradation notes."""
    marker = "## Executive Summary"
    start = markdown.find(marker)
    if start < 0:
        return None
    rest = markdown[start + len(marker) :]
    end = rest.find("\n## ")
    body = rest if end < 0 else rest[:end]
    lines = [
        line.strip()
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith(">")
    ]
    text = " ".join(lines).strip()
    return text or None


def _run(
    topic: TopicSettings,
    record: RunRecord,
    runs: RunRepository,
    results: ResultRepository,
    papers: PaperRepository,
    selections: SelectionRepository,
    store: ArtifactStore,
    reading: ReadingRepository | None = None,
    feedback: FeedbackRepository | None = None,
) -> dict[str, object]:
    stored = results.synthesis_for(record.id)
    synthesis = stored[0] if stored else None
    period_start, period_end = _period(record, stored)
    decisions = selections.decisions_for(record.id)
    selected = [decision.paper_id for decision in decisions if decision.selected]
    verdicts = {
        result.paper_id: result
        for result in results.classifications_for(record.id, active_only=True)
    }
    by_decision = {decision.paper_id: decision for decision in decisions}
    paper_ids = selected or list(verdicts)
    cards: list[dict[str, object]] = []
    for paper_id in paper_ids:
        card = _paper(
            paper_id,
            papers,
            results,
            verdicts.get(paper_id),
            by_decision.get(paper_id),
        )
        if card is not None:
            cards.append(card)
    summary = record.summary or RunSummary()
    developments = _findings(synthesis.major_developments if synthesis else [])
    stored_summary = _stored_summary(store, topic.id, period_end)
    models = summary.models_used or sorted(
        {str(card["model"]) for card in cards if card.get("model")}
    )
    errors = runs.errors_for(record.id)
    return {
        "id": record.id,
        "periodStart": period_start.isoformat(),
        "periodEnd": period_end.isoformat(),
        "status": record.status,
        "stage": record.stage,
        "stageStartedAt": record.stage_started_at.isoformat() if record.stage_started_at else None,
        "startedAt": record.started_at.isoformat(),
        "durationSeconds": record.duration_seconds or 0,
        "models": models,
        "queries": list(summary.queries),
        "modelUsage": [
            {
                "provider": usage.provider,
                "model": usage.model,
                "calls": usage.calls,
                "promptTokens": usage.prompt_tokens,
                "completionTokens": usage.completion_tokens,
                "seconds": round(usage.latency_ms / 1000),
                "fallbacks": usage.fallbacks,
            }
            for usage in summary.model_usage
        ],
        "historyPeriods": synthesis.history_periods if synthesis else 0,
        "summary": _summary(summary, len(cards), len(errors), counted=record.summary is not None),
        "errors": [_error(error) for error in errors],
        "executiveSummary": stored_summary or _fallback_summary(summary, developments, topic.name),
        "hasReport": store.exists(topic.id, "reports", report_filename(period_end)),
        "developments": developments,
        "directions": _findings(synthesis.emerging_directions if synthesis else []),
        "methods": _findings(synthesis.methods_gaining_attention if synthesis else []),
        "datasets": list(synthesis.new_datasets) if synthesis else [],
        "benchmarks": list(synthesis.new_benchmarks) if synthesis else [],
        "contradictions": _findings(synthesis.contradictions if synthesis else []),
        "changes": list(synthesis.changes_from_history) if synthesis else [],
        "gaps": [_gap(gap) for gap in results.gaps_for(record.id)],
        "ideas": [_idea(idea) for idea in results.ideas_for(record.id)],
        "readingOrder": _reading_order(cards),
        "papers": _with_votes(
            topic.id, _with_reading([_public_paper(card) for card in cards], reading), feedback
        ),
    }


def run_report(
    run_id: str, runs: RunRepository, results: ResultRepository, store: ArtifactStore
) -> tuple[str, str] | None:
    """A run's Markdown report as (download filename, text), or none when it was not written."""
    record = runs.get(run_id)
    if record is None:
        return None
    _, period_end = _period(record, results.synthesis_for(run_id))
    name = report_filename(period_end)
    if not store.exists(record.topic_id, "reports", name):
        return None
    return f"{record.topic_id}_{name}", store.read_text(record.topic_id, "reports", name)


def owned_files(
    cleared: list[RunRecord],
    staying: list[RunRecord],
    results: ResultRepository,
    store: ArtifactStore,
) -> list[tuple[str, ArtifactKind, str]]:
    """The (topic, kind, name) files only the cleared runs own: their `runs/<id>-*` files, and
    their report unless a run that stays ends on the same day and so shares that report file.
    Papers' PDFs, parsed text and analyses are library files and are never listed."""

    def report(record: RunRecord) -> tuple[str, str]:
        _, end = _period(record, results.synthesis_for(record.id))
        return record.topic_id, report_filename(end)

    shared = {report(record) for record in staying}
    files: list[tuple[str, ArtifactKind, str]] = []
    for record in cleared:
        files.extend(
            (record.topic_id, "runs", name)
            for name in store.names(record.topic_id, "runs")
            if name.startswith(f"{record.id}-")
        )
        if (owned := report(record)) not in shared:
            files.append((owned[0], "reports", owned[1]))
    return files


def _period(
    record: RunRecord, stored: tuple[WeeklySynthesis, date, date] | None
) -> tuple[date, date]:
    if stored is not None:
        return stored[1], stored[2]
    started = _as_date(record.started_at)
    finished = _as_date(record.completed_at) if record.completed_at else started
    return started, finished


def _as_date(moment: datetime) -> date:
    return moment.date()


def _summary(summary: RunSummary, cards: int, errors: int, *, counted: bool) -> dict[str, int]:
    return {
        "candidatesDiscovered": summary.candidates_discovered,
        "candidatesDeduplicated": summary.candidates_deduplicated,
        "papersClassified": summary.papers_classified,
        "papersSelected": summary.papers_selected if counted else cards,
        "downloadsSucceeded": summary.downloads_succeeded,
        "parseFailures": summary.parse_failures,
        "deepReads": summary.deep_reads,
        "errors": summary.errors if counted else errors,
    }


def _paper(
    paper_id: str,
    papers: PaperRepository,
    results: ResultRepository,
    verdict: ClassificationResult | None,
    decision: SelectionDecision | None,
) -> dict[str, object] | None:
    paper = papers.get(paper_id)
    stored_id = None if paper is None else paper.canonical_id
    if paper is None or not stored_id:
        return None
    analysis = results.analysis_for(paper_id)
    action = verdict.action if verdict else decision.action if decision else "summarize"
    return {
        "id": stored_id,
        "paper": paper,
        "analysis": analysis,
        "action": action,
        "type": verdict.paper_type if verdict else "other",
        "relevance": verdict.relevance if verdict else "medium",
        "model": analysis.model_name if analysis else None,
        "screening": _screening(verdict, decision),
        "hasPdf": "pdf" in papers.files_for(paper_id),
    }


def _public_paper(card: dict[str, object]) -> dict[str, object]:
    paper = card["paper"]
    analysis = card["analysis"]
    assert isinstance(paper, PaperCandidate)
    assert analysis is None or isinstance(analysis, PaperAnalysis)
    abstract_only = True if analysis is None else analysis.abstract_only
    return {
        "id": card["id"],
        "title": paper.title,
        "authors": list(paper.authors),
        "date": paper.publication_date.isoformat() if paper.publication_date else None,
        "venue": paper.venue,
        "doi": paper.doi,
        "arxivId": paper.arxiv_id,
        "action": card["action"],
        "type": card["type"],
        "abstractOnly": abstract_only,
        "citationCount": paper.citation_count,
        "problem": _text(
            analysis.research_problem if analysis else paper.abstract, "No analysis is stored."
        ),
        "contribution": _text(
            analysis.main_contribution if analysis else paper.abstract, "Not analysed."
        ),
        "method": analysis.method if analysis else "",
        "setup": (analysis.experimental_setup or "") if analysis else "",
        "datasets": list(analysis.datasets) if analysis else [],
        "benchmarks": list(analysis.benchmarks) if analysis else [],
        "results": list(analysis.main_results) if analysis else [],
        "strengths": list(analysis.strengths) if analysis else [],
        "limitations": list(analysis.limitations) if analysis else [],
        "relatedWork": list(analysis.related_work) if analysis else [],
        "claims": [
            {"text": claim.text, "section": claim.source_section, "page": claim.page}
            for claim in (analysis.key_claims if analysis else [])
        ],
        "relevance": analysis.topic_relevance if analysis else "",
        "screening": card["screening"],
        "hasPdf": card["hasPdf"],
    }


def _with_reading(
    cards: list[dict[str, object]], reading: ReadingRepository | None
) -> list[dict[str, object]]:
    """Attach each card's reading state, in one query for the run."""
    states = reading.states_for(str(card["id"]) for card in cards) if reading else {}
    for card in cards:
        card["reading"] = states.get(str(card["id"]), ReadingState()).model_dump()
    return cards


def _with_votes(
    topic_id: str, rows: list[dict[str, object]], feedback: FeedbackRepository | None
) -> list[dict[str, object]]:
    """Attach the reader's relevance vote for this topic (1, -1, or 0 for none)."""
    votes = feedback.votes_for(topic_id, (str(row["id"]) for row in rows)) if feedback else {}
    for row in rows:
        row["vote"] = votes.get(str(row["id"]), 0)
    return rows


def _screening(
    verdict: ClassificationResult | None, decision: SelectionDecision | None
) -> dict[str, object]:
    """Why a paper was kept or dropped: the screener's verdict and the selection decision."""
    return {
        "score": verdict.relevance_score if verdict else None,
        "level": verdict.relevance if verdict else None,
        "reason": verdict.reason_short if verdict else None,
        "decision": decision.reason if decision else None,
        "rank": decision.rank if decision else None,
    }


def screened_papers(
    run_id: str,
    results: ResultRepository,
    papers: PaperRepository,
    selections: SelectionRepository,
    *,
    topic_id: str = "",
    feedback: FeedbackRepository | None = None,
) -> list[dict[str, object]]:
    """Every paper a run screened, kept or dropped, in selection-rank order.

    Served on request rather than on the shelf: a run screens up to hundreds of papers, and the
    shelf is fetched every few seconds while a run is in flight.
    """
    verdicts = {
        result.paper_id: result for result in results.classifications_for(run_id, active_only=True)
    }
    rows: list[dict[str, object]] = []
    for decision in selections.decisions_for(run_id):
        paper = papers.get(decision.paper_id)
        if paper is None:
            continue
        rows.append(
            {
                "id": paper.canonical_id,
                "title": paper.title,
                "doi": paper.doi,
                "arxivId": paper.arxiv_id,
                "selected": decision.selected,
                **_screening(verdicts.get(decision.paper_id), decision),
            }
        )
    return _with_votes(topic_id, rows, feedback)


def _text(value: str | None, fallback: str) -> str:
    if value and value.strip():
        return value
    return fallback


def _findings(findings: list[SupportedFinding]) -> list[dict[str, object]]:
    return [
        {"text": finding.text, "paperIds": list(finding.supporting_paper_ids)}
        for finding in findings
    ]


def _gap(gap: ResearchGap) -> dict[str, object]:
    return {
        "title": gap.title,
        "description": gap.description,
        "paperIds": list(gap.supporting_paper_ids),
    }


def _idea(idea: ResearchIdea) -> dict[str, object]:
    return {
        "title": idea.title,
        "hypothesis": idea.hypothesis,
        "motivation": idea.motivation,
        "direction": idea.proposed_direction,
        "paperIds": list(idea.supporting_paper_ids),
    }


def _error(error: ErrorRecord) -> dict[str, object]:
    return {"category": error.category, "message": error.message, "paperId": error.paper_id}


def _reading_order(cards: list[dict[str, object]]) -> dict[str, list[str]]:
    """Same tiers as the weekly report: deep read, summary, then everything else."""
    tiers: dict[str, list[str]] = {"essential": [], "useful": [], "peripheral": []}
    for card in cards:
        paper_id = card["id"]
        action = card["action"]
        if not isinstance(paper_id, str):
            continue
        if action == "deep_read":
            tier = "essential"
        elif action == "summarize":
            tier = "useful"
        else:
            tier = "peripheral"
        tiers[tier].append(paper_id)
    return tiers


def _stored_summary(store: ArtifactStore, topic_id: str, period_end: date) -> str | None:
    name = report_filename(period_end)
    if not store.exists(topic_id, "reports", name):
        return None
    return executive_summary_text(store.read_text(topic_id, "reports", name))


def _fallback_summary(
    summary: RunSummary, developments: list[dict[str, object]], topic_name: str
) -> str:
    if developments:
        text = developments[0].get("text")
        if isinstance(text, str) and text.strip():
            return text
    if summary.papers_selected:
        return (
            f"{summary.papers_selected} papers were kept for {topic_name}. "
            "No weekly summary is stored yet."
        )
    return f"No weekly summary is stored yet for {topic_name}."
