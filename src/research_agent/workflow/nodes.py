"""The graph's nodes.

Each node is a coroutine taking the current state and returning only the fields it changed. Nodes
never raise: a stage that fails records an `ErrorRecord` and lets the run continue with less, which
is what keeps partial progress in a weekly run.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from research_agent.domain.runs import ErrorCategory, ErrorRecord, RunStatus, RunSummary
from research_agent.queries.planner import base_query
from research_agent.selection.selector import select
from research_agent.workflow.services import WorkflowServices
from research_agent.workflow.state import ResearchState

_LOGGER = logging.getLogger(__name__)

Update = dict[str, Any]
Node = Callable[[ResearchState], Awaitable[Any]]


def _error(
    state: ResearchState, node: str, category: ErrorCategory, message: str
) -> list[ErrorRecord]:
    """Append one error without mutating the state a node was given."""
    record = ErrorRecord(
        run_id=state.run_id or "unstarted", node=node, category=category, message=message
    )
    return [*state.errors, record]


def load_topic(services: WorkflowServices) -> Node:
    """Open the run. Everything downstream is recorded against the id this node creates."""

    async def node(state: ResearchState) -> Update:
        record = services.runs.start(
            state.topic_id,
            services.topic.classifier.active,
            services.topic.classifier.shadow,
        )
        return {"run_id": record.id}

    return node


def plan_queries(services: WorkflowServices) -> Node:
    """Expand the topic into searches; without a planner the base query alone is used."""

    async def node(state: ResearchState) -> Update:
        anchor = base_query(services.topic)
        if services.planner is None:
            return {"queries": [anchor]}
        history = services.results.recent_syntheses(state.topic_id, limit=4)
        plan = await services.planner.plan(services.topic, history)
        return {"queries": plan.queries}

    return node


def discover(services: WorkflowServices) -> Node:
    """Search every enabled source. Normalization and deduplication happen inside the aggregator."""

    async def node(state: ResearchState) -> Update:
        limit = services.topic.limits.max_candidates
        candidates = list(state.candidates)
        seen = {candidate.canonical_id for candidate in candidates}
        counts = dict(state.counts)
        errors = list(state.errors)
        for query in state.queries:
            result = await services.discovery.search(
                query, state.period_start, state.period_end, limit
            )
            for candidate in result.candidates:
                if candidate.canonical_id not in seen:
                    seen.add(candidate.canonical_id)
                    candidates.append(candidate)
            for source, found in result.counts.items():
                counts[source] = counts.get(source, 0) + found
            # The aggregator does not know the run id, so it is stamped on here; an error row
            # with a foreign key to nothing would fail the whole persist step.
            errors.extend(
                error.model_copy(update={"run_id": state.run_id or "unstarted"})
                for error in result.errors
            )
            if len(candidates) >= limit:
                break
        counts["discovered"] = len(candidates)
        return {"candidates": candidates[:limit], "counts": counts, "errors": errors}

    return node


def broaden_queries(services: WorkflowServices) -> Node:
    """The one automatic broadening pass: search the topic's own terms, separately and loosely."""

    async def node(state: ResearchState) -> Update:
        widened = [base_query(services.topic), services.topic.name, *services.topic.keywords]
        deduplicated = list(dict.fromkeys(query for query in widened if query))
        _LOGGER.info(
            "broadening discovery once",
            extra={
                "topic_id": state.topic_id,
                "run_id": state.run_id,
                "node_name": "broaden",
                "status": "retry",
            },
        )
        return {"queries": deduplicated, "broadened": True}

    return node


def classify(services: WorkflowServices) -> Node:
    """Triage with the active classifier; the shadow one is stored but never routes."""

    async def node(state: ResearchState) -> Update:
        candidates = state.candidates[: services.topic.limits.max_classified]
        outcome = await services.classifiers.run(candidates, services.topic)
        run_id = state.run_id or ""
        by_id = {candidate.canonical_id: candidate for candidate in state.candidates}
        for result, provenance in outcome.active:
            candidate = by_id.get(result.paper_id)
            if candidate is not None:
                services.papers.upsert(candidate)
            services.results.save_classification(run_id, result, raw_response=provenance)
        active_ids = {result.paper_id for result, _ in outcome.active}
        for result, provenance in outcome.shadow:
            if result.paper_id in active_ids:
                services.results.save_classification(
                    run_id, result, is_active=False, raw_response=provenance
                )
        errors = list(state.errors)
        if outcome.shadow_error:
            errors = _error(state, "classify", "CLASSIFIER_ERROR", str(outcome.shadow_error))
        counts = {**state.counts, "classified": len(outcome.active)}
        return {
            "classifications": [result for result, _ in outcome.active],
            "counts": counts,
            "errors": errors,
        }

    return node


def select_papers(services: WorkflowServices) -> Node:
    """Choose a bounded reading set, skipping papers whose text has not changed since analysis."""

    async def node(state: ResearchState) -> Update:
        analyzed = services.papers.analyzed_unchanged(
            result.paper_id for result in state.classifications
        )
        plan = select(
            state.classifications, services.topic.limits, services.settings.selection, analyzed
        )
        services.selections.save(state.run_id or "", plan)
        counts = {
            **state.counts,
            "selected": len(plan.selected_ids),
            "deep_reads": len(plan.deep_reads),
        }
        return {"selected_ids": plan.selected_ids, "counts": counts}

    return node


def acquire(services: WorkflowServices) -> Node:
    """Download the open-access PDFs that exist; a paper without one stays abstract-only."""

    async def node(state: ResearchState) -> Update:
        wanted = state.selected_ids[: services.topic.limits.max_downloads]
        papers = [paper for paper in (services.papers.get(pid) for pid in wanted) if paper]
        outcomes = await services.acquirer.acquire_many(papers, state.topic_id, state.run_id)
        paths = dict(state.pdf_paths)
        errors = list(state.errors)
        for outcome in outcomes:
            if outcome.status in ("stored", "cached") and outcome.path:
                paths[outcome.paper_id] = outcome.path
            elif outcome.status == "failed":
                errors.append(
                    ErrorRecord(
                        run_id=state.run_id or "unstarted",
                        node="acquire",
                        category="PDF_DOWNLOAD_ERROR",
                        message=outcome.reason or "download failed",
                        paper_id=outcome.paper_id,
                    )
                )
        counts = {**state.counts, "downloaded": len(paths)}
        return {"pdf_paths": paths, "counts": counts, "errors": errors}

    return node


def parse(services: WorkflowServices) -> Node:
    """Turn acquired PDFs into reusable text; a parse failure degrades that paper, not the run."""

    async def node(state: ResearchState) -> Update:
        outcomes = services.parsing.parse_many(list(state.pdf_paths), state.topic_id, state.run_id)
        paths = dict(state.parsed_paths)
        errors = list(state.errors)
        failures = 0
        for outcome in outcomes:
            if outcome.status in ("parsed", "cached") and outcome.path:
                paths[outcome.paper_id] = outcome.path
            elif outcome.status == "failed":
                failures += 1
                errors.append(
                    ErrorRecord(
                        run_id=state.run_id or "unstarted",
                        node="parse",
                        category="PDF_PARSE_ERROR",
                        message=outcome.reason or "parse failed",
                        paper_id=outcome.paper_id,
                    )
                )
        counts = {**state.counts, "parsed": len(paths), "parse_failures": failures}
        return {"parsed_paths": paths, "counts": counts, "errors": errors}

    return node


def analyze(services: WorkflowServices) -> Node:
    """Read each selected paper, from parsed text where there is any and the abstract otherwise."""

    async def node(state: ResearchState) -> Update:
        papers = [
            paper for paper in (services.papers.get(pid) for pid in state.selected_ids) if paper
        ]
        parsed = {
            paper_id: document
            for paper_id in state.parsed_paths
            if (document := services.parsing.load(paper_id, state.topic_id)) is not None
        }
        outcomes = await services.analyzer.analyze_many(
            papers, parsed, services.topic, state.run_id or ""
        )
        analyzed: list[str] = []
        abstract_only: list[str] = []
        errors = list(state.errors)
        for outcome in outcomes:
            if outcome.status in ("analyzed", "cached"):
                analyzed.append(outcome.paper_id)
                if outcome.abstract_only:
                    abstract_only.append(outcome.paper_id)
            else:
                errors.append(
                    ErrorRecord(
                        run_id=state.run_id or "unstarted",
                        node="analyze",
                        category="MODEL_API_ERROR",
                        message=outcome.reason or "analysis failed",
                        paper_id=outcome.paper_id,
                    )
                )
        counts = {**state.counts, "analyzed": len(analyzed)}
        return {
            "analyzed_ids": analyzed,
            "abstract_only_ids": abstract_only,
            "counts": counts,
            "errors": errors,
        }

    return node


def synthesize(services: WorkflowServices) -> Node:
    """Compare the week's analyses with each other and with recent history."""

    async def node(state: ResearchState) -> Update:
        analyses = [
            analysis
            for analysis in (
                services.results.analysis_for(paper_id) for paper_id in state.analyzed_ids
            )
            if analysis is not None
        ]
        titles = {
            analysis.paper_id: paper.title
            for analysis in analyses
            if (paper := services.papers.get(analysis.paper_id)) is not None
        }
        outcome = await services.synthesizer.synthesize(
            services.topic,
            state.run_id or "",
            analyses,
            titles,
            state.period_start,
            state.period_end,
        )
        if outcome.synthesis is None:
            return {
                "synthesized": False,
                "errors": _error(
                    state, "synthesize", "MODEL_API_ERROR", outcome.reason or "no synthesis"
                ),
            }
        return {"synthesized": True}

    return node


def ideate(services: WorkflowServices) -> Node:
    """Derive gaps and then ideas; both are dropped unless they cite a paper from this run."""

    async def node(state: ResearchState) -> Update:
        history = services.results.recent_syntheses(state.topic_id, limit=1)
        if not history:
            return {
                "errors": _error(
                    state, "ideate", "MODEL_API_ERROR", "no synthesis to derive gaps from"
                )
            }
        outcome = await services.ideation.generate(services.topic, state.run_id or "", history[0])
        update: Update = {"gap_count": len(outcome.gaps), "idea_count": len(outcome.ideas)}
        if not outcome.gaps:
            update["errors"] = _error(
                state, "ideate", "MODEL_API_ERROR", outcome.reason or "no supported gap"
            )
        return update

    return node


def report(services: WorkflowServices) -> Node:
    """Assemble the weekly deliverable, including the empty-week and degraded variants."""

    async def node(state: ResearchState) -> Update:
        run = services.runs.get(state.run_id or "")
        if run is None:
            return {"errors": _error(state, "report", "REPORT_ERROR", "the run record is missing")}
        outcome = await services.reports.generate(
            services.topic, run, state.selected_ids, state.period_start, state.period_end
        )
        return {"report_path": outcome.path, "empty_week": outcome.empty_week}

    return node


def persist(services: WorkflowServices) -> Node:
    """Close the run: record every tolerated error, then its summary and final status."""

    async def node(state: ResearchState) -> Update:
        run_id = state.run_id or ""
        for error in state.errors:
            services.runs.record_error(error)
        status: RunStatus = "degraded" if state.errors else "completed"
        if state.report_path is None:
            status = "failed"
        services.runs.complete(
            run_id,
            RunSummary(
                candidates_discovered=state.counts.get("discovered", 0),
                candidates_deduplicated=len(state.candidates),
                papers_classified=state.counts.get("classified", 0),
                papers_selected=state.counts.get("selected", 0),
                downloads_succeeded=state.counts.get("downloaded", 0),
                parse_failures=state.counts.get("parse_failures", 0),
                deep_reads=state.counts.get("deep_reads", 0),
                errors=len(state.errors),
            ),
            status=status,
        )
        return {"status": status}

    return node
