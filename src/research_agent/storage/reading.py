"""What the reader has done with a paper: read it, saved it, noted something.

Kept per paper rather than per run: papers are deduplicated across weeks and topics, so a paper
read once stays read, and clearing a run never loses a note.
"""

import sqlite3
from collections.abc import Iterable
from typing import Protocol

from pydantic import Field

from research_agent.config import StrictModel
from research_agent.storage.database import now_iso

MAX_NOTE_CHARS = 20_000


class ReadingState(StrictModel):
    read: bool = False
    saved: bool = False
    note: str = Field(default="", max_length=MAX_NOTE_CHARS)


class ReadingRepository(Protocol):
    """Storage-neutral repository for per-paper reading state."""

    def states_for(self, paper_ids: Iterable[str]) -> dict[str, ReadingState]: ...

    def save(self, paper_id: str, state: ReadingState) -> None: ...


class SqliteReadingRepository:
    """SQLite-backed :class:`ReadingRepository`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def states_for(self, paper_ids: Iterable[str]) -> dict[str, ReadingState]:
        """Stored state for each id that has one; an absent id is unread, unsaved, unnoted."""
        ids = list(paper_ids)
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        rows = self._connection.execute(
            f"SELECT paper_id, read, saved, note FROM reading_state "
            f"WHERE paper_id IN ({placeholders})",
            ids,
        ).fetchall()
        return {
            row["paper_id"]: ReadingState(
                read=bool(row["read"]), saved=bool(row["saved"]), note=row["note"]
            )
            for row in rows
        }

    def save(self, paper_id: str, state: ReadingState) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO reading_state (paper_id, read, saved, note, updated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(paper_id) DO UPDATE SET "
                "read = excluded.read, saved = excluded.saved, note = excluded.note, "
                "updated_at = excluded.updated_at",
                (paper_id, int(state.read), int(state.saved), state.note, now_iso()),
            )
