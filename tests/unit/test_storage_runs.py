import sqlite3

import pytest
from conftest import TOPIC_ID

from research_agent.domain.runs import ErrorRecord, RunSummary
from research_agent.storage.runs import SqliteRunRepository


def test_start_and_complete_round_trip(connection: sqlite3.Connection) -> None:
    repository = SqliteRunRepository(connection)
    run = repository.start(TOPIC_ID, active_classifier="B", shadow_classifier="A")
    assert run.status == "running"

    summary = RunSummary(
        candidates_discovered=120,
        candidates_deduplicated=90,
        papers_classified=90,
        papers_selected=12,
        downloads_succeeded=10,
        parse_failures=1,
        deep_reads=5,
        models_used=["qwen-local"],
    )
    repository.complete(run.id, summary)

    stored = repository.get(run.id)
    assert stored is not None
    assert stored.status == "completed"
    assert stored.completed_at is not None
    assert stored.duration_seconds is not None and stored.duration_seconds >= 0
    assert stored.active_classifier == "B"
    assert stored.shadow_classifier == "A"
    assert stored.summary == summary
    counts = connection.execute(
        "SELECT papers_found, papers_selected FROM runs WHERE id = ?", (run.id,)
    ).fetchone()
    assert (counts["papers_found"], counts["papers_selected"]) == (90, 12)


def test_complete_rejects_an_unknown_run(connection: sqlite3.Connection) -> None:
    with pytest.raises(KeyError):
        SqliteRunRepository(connection).complete("missing", RunSummary())


def test_get_returns_none_for_an_unknown_run(connection: sqlite3.Connection) -> None:
    assert SqliteRunRepository(connection).get("missing") is None


def test_recent_returns_newest_first(connection: sqlite3.Connection) -> None:
    repository = SqliteRunRepository(connection)
    runs = [repository.start(TOPIC_ID) for _ in range(5)]

    recent = repository.recent(TOPIC_ID, limit=3)

    assert [run.id for run in recent] == [run.id for run in reversed(runs[-3:])]


def test_errors_persist_category_and_recoverability(connection: sqlite3.Connection) -> None:
    repository = SqliteRunRepository(connection)
    run = repository.start(TOPIC_ID)

    repository.record_error(
        ErrorRecord(
            run_id=run.id,
            node="discover",
            category="RATE_LIMIT",
            message="openalex returned 429",
        )
    )
    repository.record_error(
        ErrorRecord(
            run_id=run.id,
            node="parse",
            category="PDF_PARSE_ERROR",
            message="unreadable pdf",
            recoverable=False,
            paper_id="doi_10_1234_abcd",
        )
    )

    errors = repository.errors_for(run.id)
    assert [error.category for error in errors] == ["RATE_LIMIT", "PDF_PARSE_ERROR"]
    assert [error.recoverable for error in errors] == [True, False]
    assert errors[1].paper_id == "doi_10_1234_abcd"
    assert errors[0].occurred_at is not None


def test_a_failed_transaction_leaves_no_run(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError), connection:
        connection.execute(
            "INSERT INTO runs (id, topic_id, started_at, status, active_classifier) "
            "VALUES ('r1', ?, '2026-09-22T00:00:00+00:00', 'running', 'A')",
            (TOPIC_ID,),
        )
        connection.execute(
            "INSERT INTO runs (id, topic_id, started_at, status, active_classifier) "
            "VALUES ('r1', ?, '2026-09-22T00:00:00+00:00', 'running', 'A')",
            (TOPIC_ID,),
        )

    assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
