"""Run lifecycle and error persistence behind a repository interface."""

import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Literal, Protocol

from research_agent.domain.runs import ErrorRecord, RunRecord, RunStatus, RunSummary

_RUN_COLUMNS = (
    "id, topic_id, started_at, completed_at, status, active_classifier, "
    "shadow_classifier, duration_seconds, summary_json"
)


class RunRepository(Protocol):
    """Storage-neutral run and error repository."""

    def start(
        self,
        topic_id: str,
        active_classifier: Literal["A", "B"] = "A",
        shadow_classifier: Literal["A", "B"] | None = None,
    ) -> RunRecord: ...

    def complete(
        self, run_id: str, summary: RunSummary, status: RunStatus = "completed"
    ) -> None: ...

    def get(self, run_id: str) -> RunRecord | None: ...

    def recent(self, topic_id: str, limit: int = 4) -> list[RunRecord]: ...

    def record_error(self, error: ErrorRecord) -> None: ...

    def errors_for(self, run_id: str) -> list[ErrorRecord]: ...


def _from_row(row: sqlite3.Row) -> RunRecord:
    completed = row["completed_at"]
    summary = row["summary_json"]
    return RunRecord(
        id=row["id"],
        topic_id=row["topic_id"],
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=datetime.fromisoformat(completed) if completed else None,
        status=row["status"],
        active_classifier=row["active_classifier"],
        shadow_classifier=row["shadow_classifier"],
        duration_seconds=row["duration_seconds"],
        summary=RunSummary.model_validate_json(summary) if summary else None,
    )


class SqliteRunRepository:
    """SQLite-backed :class:`RunRepository`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def start(
        self,
        topic_id: str,
        active_classifier: Literal["A", "B"] = "A",
        shadow_classifier: Literal["A", "B"] | None = None,
    ) -> RunRecord:
        record = RunRecord(
            id=uuid.uuid4().hex,
            topic_id=topic_id,
            started_at=datetime.now(UTC),
            active_classifier=active_classifier,
            shadow_classifier=shadow_classifier,
        )
        with self._connection:
            self._connection.execute(
                "INSERT INTO runs (id, topic_id, started_at, status, active_classifier, "
                "   shadow_classifier) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.topic_id,
                    record.started_at.isoformat(),
                    record.status,
                    record.active_classifier,
                    record.shadow_classifier,
                ),
            )
        return record

    def complete(self, run_id: str, summary: RunSummary, status: RunStatus = "completed") -> None:
        """Close a run, deriving its duration from the stored start time."""
        started = self._connection.execute(
            "SELECT started_at FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        if started is None:
            raise KeyError(f"unknown run: {run_id}")
        completed_at = datetime.now(UTC)
        duration = (completed_at - datetime.fromisoformat(started["started_at"])).total_seconds()
        with self._connection:
            self._connection.execute(
                "UPDATE runs SET completed_at = ?, status = ?, duration_seconds = ?, "
                "   papers_found = ?, papers_selected = ?, summary_json = ? WHERE id = ?",
                (
                    completed_at.isoformat(),
                    status,
                    duration,
                    summary.candidates_deduplicated,
                    summary.papers_selected,
                    summary.model_dump_json(),
                    run_id,
                ),
            )

    def get(self, run_id: str) -> RunRecord | None:
        row = self._connection.execute(
            f"SELECT {_RUN_COLUMNS} FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
        return None if row is None else _from_row(row)

    def recent(self, topic_id: str, limit: int = 4) -> list[RunRecord]:
        rows = self._connection.execute(
            f"SELECT {_RUN_COLUMNS} FROM runs WHERE topic_id = ? "
            "ORDER BY started_at DESC, id DESC LIMIT ?",
            (topic_id, limit),
        ).fetchall()
        return [_from_row(row) for row in rows]

    def record_error(self, error: ErrorRecord) -> None:
        """Persist a categorized failure. Unknown paper ids are stored as-is, not enforced."""
        with self._connection:
            self._connection.execute(
                "INSERT INTO errors (id, run_id, paper_id, node, category, recoverable, "
                "   message, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    error.run_id,
                    error.paper_id,
                    error.node,
                    error.category,
                    int(error.recoverable),
                    error.message,
                    (error.occurred_at or datetime.now(UTC)).isoformat(),
                ),
            )

    def errors_for(self, run_id: str) -> list[ErrorRecord]:
        rows = self._connection.execute(
            "SELECT run_id, paper_id, node, category, recoverable, message, created_at "
            "FROM errors WHERE run_id = ? ORDER BY created_at, id",
            (run_id,),
        ).fetchall()
        return [
            ErrorRecord(
                run_id=row["run_id"],
                paper_id=row["paper_id"],
                node=row["node"],
                category=row["category"],
                message=row["message"],
                recoverable=bool(row["recoverable"]),
                occurred_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]
