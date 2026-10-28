"""Ask conversations, kept per run and per paper so a follow-up question sees the earlier turns.

A thread belongs to one run: clearing the run deletes its conversations with it. `paper_id` is
empty for a question about the whole week.
"""

import json
import sqlite3
from datetime import datetime
from typing import Protocol

from pydantic import Field

from research_agent.config import StrictModel
from research_agent.storage.database import now_iso


class AskTurn(StrictModel):
    """One question and the answer it got."""

    question: str = Field(min_length=1)
    paragraphs: list[str] = Field(min_length=1)
    cites: list[dict[str, str]] = Field(default_factory=list)
    note: str = ""
    asked_at: datetime | None = None


class AskRepository(Protocol):
    """Storage-neutral repository for Ask threads."""

    def turns(self, run_id: str, paper_id: str | None) -> list[AskTurn]: ...

    def add(self, run_id: str, paper_id: str | None, turn: AskTurn) -> None: ...

    def clear(self, run_id: str, paper_id: str | None) -> int: ...


class SqliteAskRepository:
    """SQLite-backed :class:`AskRepository`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def turns(self, run_id: str, paper_id: str | None) -> list[AskTurn]:
        """The thread, oldest turn first."""
        rows = self._connection.execute(
            "SELECT question, answer_json, asked_at FROM ask_turns "
            "WHERE run_id = ? AND paper_id = ? ORDER BY id",
            (run_id, paper_id or ""),
        ).fetchall()
        return [
            AskTurn.model_validate(
                {
                    **json.loads(row["answer_json"]),
                    "question": row["question"],
                    "asked_at": row["asked_at"],
                }
            )
            for row in rows
        ]

    def add(self, run_id: str, paper_id: str | None, turn: AskTurn) -> None:
        answer = turn.model_dump(include={"paragraphs", "cites", "note"})
        with self._connection:
            self._connection.execute(
                "INSERT INTO ask_turns (run_id, paper_id, question, answer_json, asked_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (run_id, paper_id or "", turn.question, json.dumps(answer), now_iso()),
            )

    def clear(self, run_id: str, paper_id: str | None) -> int:
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM ask_turns WHERE run_id = ? AND paper_id = ?",
                (run_id, paper_id or ""),
            )
        return cursor.rowcount
