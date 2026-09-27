import asyncio
import json
import sqlite3
from datetime import date
from pathlib import Path

import httpx
import pytest

from research_agent.config import ApplicationSettings, ReportSettings, TopicSettings
from research_agent.domain.analysis import PaperAnalysis
from research_agent.models.router import build_router
from research_agent.reports.service import ReportOutcome, ReportService
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from tests.unit.conftest import TOPIC_ID, candidate, mock_client

START = date(2026, 9, 17)
END = date(2026, 9, 27)


def topic() -> TopicSettings:
    return TopicSettings.model_validate({"id": TOPIC_ID, "name": "Spatial Intelligence"})


def analysis(paper_id: str) -> PaperAnalysis:
    return PaperAnalysis(
        paper_id=paper_id,
        research_problem="Agents cannot reason about unseen rooms.",
        main_contribution="A spatial memory module.",
        method="A transformer over a metric map.",
        topic_relevance="Directly on topic.",
        model_provider="local",
        model_name="qwen",
        prompt_version="paper_analysis.v1",
    )


def replying(content: str) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": content}}]}
        )

    return handler


def failing(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, json={"error": "upstream is unwell"})


def service(
    connection: sqlite3.Connection,
    tmp_path: Path,
    handler: object | None = None,
    settings: ReportSettings | None = None,
) -> ReportService:
    router = (
        None
        if handler is None
        else build_router(
            mock_client(handler),  # type: ignore[arg-type]
            ApplicationSettings(),
        )
    )
    return ReportService(
        LocalArtifactStore(tmp_path / "data"),
        SqliteResultRepository(connection),
        SqlitePaperRepository(connection),
        SqliteRunRepository(connection),
        router,
        settings,
    )


@pytest.fixture
def analyzed(connection: sqlite3.Connection) -> str:
    """One run with a stored paper and a stored analysis, ready to report on."""
    run_id = SqliteRunRepository(connection).start(TOPIC_ID, "A").id
    papers = SqlitePaperRepository(connection)
    paper_id = papers.upsert(candidate(doi="10.1234/abcd"))
    SqliteResultRepository(connection).save_analysis(run_id, analysis(paper_id))
    return run_id


def generate(
    connection: sqlite3.Connection,
    reports: ReportService,
    run_id: str,
    paper_ids: list[str],
) -> ReportOutcome:
    record = SqliteRunRepository(connection).get(run_id)
    assert record is not None
    return asyncio.run(reports.generate(topic(), record, paper_ids, START, END))


def test_a_report_is_written_with_model_written_prose(
    connection: sqlite3.Connection, tmp_path: Path, analyzed: str
) -> None:
    handler = replying(json.dumps({"executive_summary": "One paper advanced spatial memory."}))

    outcome = generate(
        connection, service(connection, tmp_path, handler), analyzed, ["doi_10_1234_abcd"]
    )

    assert (outcome.papers, outcome.empty_week, outcome.prose) == (1, False, True)
    assert outcome.path.endswith("2026-09-27_weekly_report.md")
    text = Path(outcome.path).read_text(encoding="utf-8")
    assert "One paper advanced spatial memory." in text
    assert "doi_10_1234_abcd" in text


def test_a_provider_failure_still_produces_a_report(
    connection: sqlite3.Connection, tmp_path: Path, analyzed: str
) -> None:
    outcome = generate(
        connection, service(connection, tmp_path, failing), analyzed, ["doi_10_1234_abcd"]
    )

    assert outcome.prose is False
    assert "No model-written summary was available" in Path(outcome.path).read_text(
        encoding="utf-8"
    )


def test_prose_can_be_switched_off(
    connection: sqlite3.Connection, tmp_path: Path, analyzed: str
) -> None:
    handler = replying(json.dumps({"executive_summary": "Unused."}))
    reports = service(connection, tmp_path, handler, ReportSettings(include_prose=False))

    outcome = generate(connection, reports, analyzed, ["doi_10_1234_abcd"])

    assert outcome.prose is False
    assert "Unused." not in Path(outcome.path).read_text(encoding="utf-8")


def test_an_empty_week_is_reported_without_a_model_call(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": []})

    run_id = SqliteRunRepository(connection).start(TOPIC_ID, "A").id

    outcome = generate(connection, service(connection, tmp_path, handler), run_id, [])

    assert (outcome.empty_week, outcome.papers, calls) == (True, 0, 0)
    assert "No paper met this period" in Path(outcome.path).read_text(encoding="utf-8")


def test_regenerating_replaces_the_period_report_in_place(
    connection: sqlite3.Connection, tmp_path: Path, analyzed: str
) -> None:
    reports = service(connection, tmp_path)
    first = generate(connection, reports, analyzed, ["doi_10_1234_abcd"])

    second = generate(connection, reports, analyzed, ["doi_10_1234_abcd"])

    assert first.path == second.path
    directory = Path(first.path).parent
    assert [path.name for path in directory.iterdir()] == ["2026-09-27_weekly_report.md"]


def test_latest_picks_the_newest_report_and_ignores_other_artifacts(
    connection: sqlite3.Connection, tmp_path: Path, analyzed: str
) -> None:
    reports = service(connection, tmp_path)
    store = LocalArtifactStore(tmp_path / "data")
    generate(connection, reports, analyzed, ["doi_10_1234_abcd"])
    store.write_text(TOPIC_ID, "reports", "2026-10-04_weekly_report.md", "# later")
    store.write_text(TOPIC_ID, "reports", "notes.md", "# not a report")

    latest = reports.latest(TOPIC_ID)

    assert latest is not None and latest.endswith("2026-10-04_weekly_report.md")


def test_latest_returns_nothing_for_a_topic_without_reports(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    assert service(connection, tmp_path).latest(TOPIC_ID) is None


def test_a_degraded_run_is_marked_in_the_outcome(
    connection: sqlite3.Connection, tmp_path: Path, analyzed: str
) -> None:
    from research_agent.domain.runs import ErrorRecord

    SqliteRunRepository(connection).record_error(
        ErrorRecord(
            run_id=analyzed,
            node="acquire",
            category="PDF_DOWNLOAD_ERROR",
            message="no open-access PDF",
        )
    )

    outcome = generate(connection, service(connection, tmp_path), analyzed, ["doi_10_1234_abcd"])

    assert outcome.degraded
    assert "> Degraded run:" in Path(outcome.path).read_text(encoding="utf-8")
