import asyncio
import sqlite3
from datetime import date
from pathlib import Path

import httpx
import pytest

from research_agent.config import ApplicationSettings, TopicSettings
from research_agent.operations import runner as operations
from research_agent.operations.locks import lock_path
from research_agent.operations.runner import RunOutcome, execute_run, reporting_period
from research_agent.storage.runs import SqliteRunRepository
from research_agent.workflow.state import ResearchState
from tests.unit.conftest import TOPIC_ID

TODAY = date(2026, 9, 27)


def topic(**overrides: object) -> TopicSettings:
    payload: dict[str, object] = {"id": TOPIC_ID, "name": "Spatial Intelligence"}
    payload.update(overrides)
    return TopicSettings.model_validate(payload)


def settings(tmp_path: Path) -> ApplicationSettings:
    return ApplicationSettings(data_directory=tmp_path / "data")


def client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    )


def run(
    connection: sqlite3.Connection, tmp_path: Path, subject: TopicSettings | None = None
) -> RunOutcome:
    return asyncio.run(
        execute_run(
            connection,
            settings(tmp_path),
            subject or topic(),
            client_factory=client,
            parser=object(),
            today=TODAY,
        )
    )


def test_the_reporting_period_is_the_topic_lookback() -> None:
    start, end = reporting_period(topic(lookback_days=10), TODAY)

    assert (start.isoformat(), end.isoformat()) == ("2026-09-17", "2026-09-27")


def test_a_disabled_topic_is_skipped_without_touching_the_database(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    outcome = run(connection, tmp_path, topic(enabled=False))

    assert (outcome.conclusion, outcome.fatal) == ("skipped", False)
    assert SqliteRunRepository(connection).recent(TOPIC_ID) == []


def test_a_held_lock_refuses_the_run(connection: sqlite3.Connection, tmp_path: Path) -> None:
    path = lock_path(tmp_path / "data", TOPIC_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not a pid", encoding="utf-8")

    outcome = run(connection, tmp_path)

    assert outcome.conclusion == "locked"
    assert outcome.reason is not None and "in progress" in outcome.reason


def test_the_outcome_reflects_the_final_state(
    connection: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_workflow(services: object, start: date, end: date) -> ResearchState:
        return ResearchState(
            topic_id=TOPIC_ID,
            period_start=start,
            period_end=end,
            run_id="run1",
            analyzed_ids=["p1", "p2"],
            report_path="/tmp/report.md",
            status="degraded",
        )

    monkeypatch.setattr(operations, "run_workflow", fake_workflow)

    outcome = run(connection, tmp_path)

    assert outcome.conclusion == "degraded"
    assert (outcome.papers_analyzed, outcome.report_path) == (2, "/tmp/report.md")
    assert outcome.fatal is False, "a degraded run still delivered a report"


def test_a_cancelled_run_is_closed_as_failed(
    connection: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = SqliteRunRepository(connection).start(TOPIC_ID, "A")

    async def cancelled(services: object, start: date, end: date) -> ResearchState:
        raise asyncio.CancelledError

    monkeypatch.setattr(operations, "run_workflow", cancelled)

    outcome = run(connection, tmp_path)

    assert outcome.conclusion == "failed"
    record = SqliteRunRepository(connection).get(started.id)
    assert record is not None and record.status == "failed"


def test_an_interrupted_run_is_closed_as_failed(
    connection: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = SqliteRunRepository(connection).start(TOPIC_ID, "A")

    async def interrupted(services: object, start: date, end: date) -> ResearchState:
        raise KeyboardInterrupt

    monkeypatch.setattr(operations, "run_workflow", interrupted)

    outcome = run(connection, tmp_path)

    assert outcome.conclusion == "failed" and outcome.fatal
    assert outcome.reason is not None and "interrupted" in outcome.reason
    record = SqliteRunRepository(connection).get(started.id)
    assert record is not None and record.status == "failed"
    assert not lock_path(tmp_path / "data", TOPIC_ID).exists(), "the lock is always released"
