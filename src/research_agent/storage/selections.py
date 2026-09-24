"""Selection persistence: what a run chose to read, and why it dropped the rest."""

import sqlite3
import uuid
from typing import Protocol

from research_agent.domain.selection import SelectionDecision, SelectionPlan
from research_agent.storage.database import now_iso


class SelectionRepository(Protocol):
    """Storage-neutral repository for selection decisions."""

    def save(self, run_id: str, plan: SelectionPlan) -> None: ...

    def decisions_for(self, run_id: str) -> list[SelectionDecision]: ...

    def selected_for(self, run_id: str) -> list[str]: ...


class SqliteSelectionRepository:
    """SQLite-backed :class:`SelectionRepository`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, run_id: str, plan: SelectionPlan) -> None:
        """Store every decision, kept or dropped, so a past run stays explainable."""
        timestamp = now_iso()
        with self._connection:
            self._connection.executemany(
                "INSERT INTO selections (id, run_id, paper_id, rank, selected, action, reason, "
                "   created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        uuid.uuid4().hex,
                        run_id,
                        decision.paper_id,
                        decision.rank,
                        int(decision.selected),
                        decision.action,
                        decision.reason,
                        timestamp,
                    )
                    for decision in plan.decisions
                ],
            )

    def decisions_for(self, run_id: str) -> list[SelectionDecision]:
        rows = self._connection.execute(
            "SELECT paper_id, rank, selected, action, reason FROM selections "
            "WHERE run_id = ? ORDER BY rank",
            (run_id,),
        ).fetchall()
        return [
            SelectionDecision(
                paper_id=row["paper_id"],
                rank=row["rank"],
                selected=bool(row["selected"]),
                action=row["action"],
                reason=row["reason"],
            )
            for row in rows
        ]

    def selected_for(self, run_id: str) -> list[str]:
        """The reading set, in rank order; this is what F11 downloads."""
        rows = self._connection.execute(
            "SELECT paper_id FROM selections WHERE run_id = ? AND selected = 1 ORDER BY rank",
            (run_id,),
        ).fetchall()
        return [row["paper_id"] for row in rows]
