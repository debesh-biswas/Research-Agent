"""The complete LangGraph run, fully mocked.

Every service is the real one; only the network, the model endpoint and the PDF parser are faked, so
this exercises the graph's wiring, its conditional branches and its failure isolation together.
"""

import asyncio
import json
import sqlite3
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx

from research_agent.analysis.analyzer import PaperAnalyzer
from research_agent.config import ApplicationSettings, RetrySettings, TopicSettings
from research_agent.discovery.aggregator import DiscoveryAggregator, build_sources
from research_agent.documents.downloader import PdfDownloader
from research_agent.documents.parser import ParsingService
from research_agent.domain.documents import ParsedPaper, ParsedSection
from research_agent.ideation.generator import IdeationService
from research_agent.models.router import build_router
from research_agent.queries.planner import QueryPlanner
from research_agent.reports.service import ReportService
from research_agent.screening.service import PaperScreener
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from research_agent.storage.selections import SqliteSelectionRepository
from research_agent.synthesis.synthesizer import WeeklySynthesizer
from research_agent.workflow.graph import run_workflow
from research_agent.workflow.services import WorkflowServices
from research_agent.workflow.state import ResearchState
from tests.integration.conftest import graph_topic
from tests.unit.conftest import mock_client

START = date(2026, 9, 17)
END = date(2026, 9, 27)
PDF = b"%PDF-1.7\n" + b"x" * 200

Handler = Callable[[httpx.Request], httpx.Response]

_PAPERS = [
    {
        "id": "https://openalex.org/W1",
        "display_name": "Spatial Intelligence for Embodied Navigation",
        "doi": "https://doi.org/10.1234/abcd",
        "publication_date": "2026-09-18",
        "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
        "primary_location": {"pdf_url": "https://example.org/one.pdf"},
    },
    {
        "id": "https://openalex.org/W2",
        "display_name": "Metric Control Benchmarks for Manipulation",
        "doi": "https://doi.org/10.1234/efgh",
        "publication_date": "2026-09-20",
        "authorships": [{"author": {"display_name": "Grace Hopper"}}],
        "primary_location": {"pdf_url": "https://example.org/two.pdf"},
    },
]
DRAFT: dict[str, object] = {
    "research_problem": "Agents cannot reason about unseen rooms.",
    "main_contribution": "A persistent spatial memory module.",
    "method": "A transformer over a metric map.",
    "main_results": ["+7 SPL over the baseline"],
    "topic_relevance": "Directly on topic.",
}
SCREENING: dict[str, object] = {
    "relevance": "high",
    "relevance_score": 0.9,
    "paper_type": "method",
    "action": "deep_read",
    "confidence": 0.9,
    "reason_short": "The central contribution is directly on topic.",
}
SYNTHESIS: dict[str, object] = {
    "major_developments": [
        {"text": "Metric control is benchmarked", "supporting_paper_ids": ["doi_10_1234_abcd"]}
    ],
    "new_benchmarks": ["ObjectNav"],
}
GAPS: dict[str, object] = {
    "gaps": [
        {
            "title": "No long-horizon benchmark",
            "description": "Benchmarks stop at 50 steps.",
            "supporting_paper_ids": ["doi_10_1234_abcd"],
            "confidence": 0.6,
        }
    ]
}
IDEAS: dict[str, object] = {
    "ideas": [
        {
            "title": "Persistent map benchmark",
            "hypothesis": "Longer horizons expose memory failures.",
            "motivation": "Scores saturate.",
            "supporting_paper_ids": ["doi_10_1234_abcd"],
            "identified_gap": "No long-horizon benchmark",
            "proposed_direction": "Extend episodes.",
            "evaluation_plan": "Compare SPL across horizons.",
            "risks": ["Compute cost"],
        }
    ]
}


class FakeParser:
    name = "fake"

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    def parse(self, pdf_path: Path, paper_id: str) -> ParsedPaper:
        if self._error is not None:
            raise self._error
        return ParsedPaper(
            paper_id=paper_id,
            source_pdf_path=str(pdf_path),
            sections=[ParsedSection(title="Results", text="SPL rises from 0.51 to 0.58.", page=2)],
            parser_name=self.name,
            parser_version="1.0",
        )


def completion(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"role": "assistant", "content": json.dumps(payload)}}]},
    )


def handler(
    papers: list[dict[str, object]] | None = None,
    *,
    pdf: bool = True,
    model: bool = True,
) -> Handler:
    """One transport for discovery, PDFs and the model endpoint, with each part switchable off."""
    results = _PAPERS if papers is None else papers

    def respond(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith(".pdf"):
            if not pdf:
                return httpx.Response(404, text="gone")
            return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
        if url.endswith("/chat/completions"):
            if not model:
                return httpx.Response(503, json={"error": "upstream is unwell"})
            prompt = str(json.loads(request.content)["messages"]).lower()
            if "return relevance, relevance_score" in prompt:
                return completion(SCREENING)
            if "compare this week" in prompt:
                return completion(SYNTHESIS)
            if "identify unaddressed research questions" in prompt:
                return completion(GAPS)
            if "turn identified research gaps" in prompt:
                return completion(IDEAS)
            if "executive summary" in prompt:
                return completion({"executive_summary": "One paper advanced spatial memory."})
            if "expand" in prompt or "search queries" in prompt:
                return completion({"queries": ["embodied spatial intelligence"]})
            return completion(DRAFT)
        return httpx.Response(200, json={"meta": {"next_cursor": None}, "results": results})

    return respond


def topic() -> TopicSettings:
    return graph_topic()


def services(
    connection: sqlite3.Connection,
    tmp_path: Path,
    respond: Handler,
    parser: FakeParser | None = None,
    planner: bool = False,
) -> WorkflowServices:
    # Retry ceilings and their backoff are covered by the F5/F6 tests; here they would only make
    # the failure branches slow.
    settings = ApplicationSettings(
        data_directory=tmp_path / "data",
        retries=RetrySettings(academic_apis=0, nim=0, pdf_download=0),
    )
    client = mock_client(respond)
    store = LocalArtifactStore(settings.data_directory)
    papers = SqlitePaperRepository(connection)
    results = SqliteResultRepository(connection)
    runs = SqliteRunRepository(connection)
    router = build_router(client, settings)
    return WorkflowServices(
        settings=settings,
        topic=topic(),
        runs=runs,
        papers=papers,
        results=results,
        selections=SqliteSelectionRepository(connection),
        discovery=DiscoveryAggregator(
            build_sources(client, settings, topic().discovery), settings=settings
        ),
        screener=PaperScreener(build_router(client, settings), settings),
        acquirer=PdfDownloader(client, store, papers, settings.documents),
        parsing=ParsingService(parser or FakeParser(), store, papers),
        analyzer=PaperAnalyzer(router, results, papers, store, settings.analysis),
        synthesizer=WeeklySynthesizer(router, results, settings.synthesis),
        ideation=IdeationService(router, results, settings.ideation),
        reports=ReportService(store, results, papers, runs, router, settings.reports),
        store=store,
        planner=QueryPlanner(router, settings.queries) if planner else None,
    )


def execute(workflow: WorkflowServices) -> ResearchState:
    return asyncio.run(run_workflow(workflow, START, END))


def test_a_complete_run_produces_a_report_and_a_closed_run(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    final = execute(services(connection, tmp_path, handler()))

    assert final.run_id is not None
    assert final.candidates and final.selected_ids
    assert final.pdf_paths and final.parsed_paths
    assert final.analyzed_ids and final.synthesized
    assert (final.gap_count, final.idea_count) == (1, 1)
    assert final.report_path is not None and Path(final.report_path).is_file()
    assert final.status == "completed"
    record = SqliteRunRepository(connection).get(final.run_id)
    assert record is not None and record.status == "completed"
    assert record.summary is not None and record.summary.papers_selected == len(final.selected_ids)


def test_the_report_of_a_complete_run_contains_the_findings(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    final = execute(services(connection, tmp_path, handler()))

    assert final.report_path is not None
    report = Path(final.report_path).read_text(encoding="utf-8")
    assert "One paper advanced spatial memory." in report
    assert "Metric control is benchmarked" in report
    assert "## Potential Research Ideas" in report


def test_empty_discovery_broadens_once_and_then_reports_an_empty_week(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    requests: list[str] = []
    base = handler(papers=[])

    def counting(request: httpx.Request) -> httpx.Response:
        if "openalex" in str(request.url):
            requests.append(str(request.url))
        return base(request)

    final = execute(services(connection, tmp_path, counting))

    assert final.broadened is True
    assert final.candidates == [] and final.empty_week is True
    assert final.report_path is not None
    assert "No paper met this period" in Path(final.report_path).read_text(encoding="utf-8")
    assert len(requests) > 1, "broadening must issue further searches"
    assert final.status == "completed"


def test_a_failed_download_leaves_the_paper_abstract_only(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    final = execute(services(connection, tmp_path, handler(pdf=False)))

    assert final.pdf_paths == {} and final.parsed_paths == {}
    assert final.analyzed_ids
    assert set(final.abstract_only_ids) == set(final.analyzed_ids)
    assert final.status == "degraded"
    errors = SqliteRunRepository(connection).errors_for(final.run_id or "")
    assert {error.category for error in errors} == {"PDF_DOWNLOAD_ERROR"}


def test_a_parse_failure_is_isolated_and_recorded(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    final = execute(
        services(connection, tmp_path, handler(), FakeParser(error=RuntimeError("corrupt xref")))
    )

    assert final.pdf_paths and final.parsed_paths == {}
    assert final.analyzed_ids and final.abstract_only_ids
    assert final.status == "degraded"
    errors = SqliteRunRepository(connection).errors_for(final.run_id or "")
    assert {error.category for error in errors} == {"PDF_PARSE_ERROR"}


def test_a_dead_model_provider_still_produces_a_report(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    final = execute(services(connection, tmp_path, handler(model=False)))

    assert final.analyzed_ids == []
    assert final.synthesized is False
    assert final.report_path is not None and Path(final.report_path).is_file()
    assert final.status == "degraded"
    categories = {
        error.category for error in SqliteRunRepository(connection).errors_for(final.run_id or "")
    }
    assert "MODEL_API_ERROR" in categories


def test_a_failing_source_does_not_end_the_run(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    def flaky(request: httpx.Request) -> httpx.Response:
        if "openalex" in str(request.url):
            return httpx.Response(500, text="upstream is unwell")
        return handler()(request)

    final = execute(services(connection, tmp_path, flaky))

    assert final.candidates == []
    assert final.report_path is not None
    assert final.status == "degraded"


def test_a_planner_expands_the_queries_it_is_given(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    final = execute(services(connection, tmp_path, handler(), planner=True))

    assert final.queries, "the plan must reach the state"
    assert final.report_path is not None


def test_a_second_run_reuses_the_stored_analyses(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    first = execute(services(connection, tmp_path, handler()))

    second = execute(services(connection, tmp_path, handler()))

    assert first.run_id != second.run_id
    assert second.selected_ids == [], "papers whose text has not changed are not re-read"
    assert second.empty_week is True
    assert second.report_path is not None
