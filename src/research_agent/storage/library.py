"""Every paper the desk has kept, across topics and runs, one row per paper.

A paper kept in several runs appears once, under the newest run that kept it, so the library reads
as a reading list rather than a log.
"""

import sqlite3
from datetime import datetime
from typing import Protocol

from pydantic import Field

from research_agent.config import StrictModel


class LibraryEntry(StrictModel):
    paper_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    topic_id: str = Field(min_length=1)
    topic_name: str
    run_started_at: datetime
    action: str


class LibraryRepository(Protocol):
    def page(
        self,
        *,
        topic_id: str | None = None,
        unread_only: bool = False,
        saved_only: bool = False,
        search: str = "",
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[int, list[LibraryEntry]]: ...


class SqliteLibraryRepository:
    """SQLite-backed :class:`LibraryRepository`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def page(
        self,
        *,
        topic_id: str | None = None,
        unread_only: bool = False,
        saved_only: bool = False,
        search: str = "",
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[int, list[LibraryEntry]]:
        """One page, newest run first, plus how many papers match in total.

        `search` matches when every word appears in the title, authors, venue, abstract or any
        stored analysis of the paper, ignoring case.
        """
        conditions = ["latest.position = 1"]
        values: list[object] = []
        if topic_id:
            conditions.append("latest.topic_id = ?")
            values.append(topic_id)
        if unread_only:
            conditions.append("COALESCE(state.read, 0) = 0")
        if saved_only:
            conditions.append("COALESCE(state.saved, 0) = 1")
        for word in search.split():
            conditions.append(_MATCHES_WORD)
            values.extend([f"%{_escape_like(word)}%"] * 3)
        matching = (
            "WITH latest AS ("
            "  SELECT s.paper_id, s.action, s.rank, r.id AS run_id, r.topic_id, r.started_at,"
            "    ROW_NUMBER() OVER (PARTITION BY s.paper_id ORDER BY r.started_at DESC, r.id) "
            "      AS position"
            "  FROM selections s JOIN runs r ON r.id = s.run_id WHERE s.selected = 1"
            ") SELECT latest.*, t.name AS topic_name FROM latest"
            " JOIN topics t ON t.id = latest.topic_id"
            " JOIN papers p ON p.id = latest.paper_id"
            " LEFT JOIN reading_state state ON state.paper_id = latest.paper_id"
            f" WHERE {' AND '.join(conditions)}"
        )
        total = self._connection.execute(f"SELECT COUNT(*) FROM ({matching})", values).fetchone()[0]
        rows = self._connection.execute(
            f"{matching} ORDER BY latest.started_at DESC, latest.rank, latest.paper_id "
            "LIMIT ? OFFSET ?",
            [*values, limit, offset],
        ).fetchall()
        return total, [
            LibraryEntry(
                paper_id=row["paper_id"],
                run_id=row["run_id"],
                topic_id=row["topic_id"],
                topic_name=row["topic_name"],
                run_started_at=datetime.fromisoformat(row["started_at"]),
                action=row["action"],
            )
            for row in rows
        ]


# A word matches the paper's text, one of its authors (decoded by json_each, so "José" is found
# though authors_json stores it escaped), or any stored analysis (method, datasets, results, …).
_MATCHES_WORD = (
    "((p.title || ' ' || COALESCE(p.venue, '') || ' ' || COALESCE(p.abstract, '')) "
    "LIKE ? ESCAPE '\\'"
    " OR EXISTS (SELECT 1 FROM json_each(p.authors_json) WHERE value LIKE ? ESCAPE '\\')"
    " OR EXISTS (SELECT 1 FROM paper_analyses a WHERE a.paper_id = latest.paper_id"
    " AND a.payload_json LIKE ? ESCAPE '\\'))"
)


def _escape_like(word: str) -> str:
    """A typed `%` or `_` is a character to find, not a wildcard."""
    return word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
