"""The reader's relevance votes, per topic: the examples screening learns the topic from.

A vote steers the screening prompt only; nothing is trained (AGENTS.md rules out classifier
training). Kept per topic because a paper can be on-topic for one topic and off-topic for another.
"""

import sqlite3
from collections.abc import Iterable
from typing import Protocol

from research_agent.domain.feedback import FeedbackExamples, Vote
from research_agent.storage.database import now_iso


class FeedbackRepository(Protocol):
    """Storage-neutral repository for relevance votes."""

    def set_vote(self, topic_id: str, paper_id: str, vote: Vote | None) -> None: ...

    def votes_for(self, topic_id: str, paper_ids: Iterable[str]) -> dict[str, Vote]: ...

    def examples(self, topic_id: str, per_side: int) -> FeedbackExamples: ...


class SqliteFeedbackRepository:
    """SQLite-backed :class:`FeedbackRepository`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def set_vote(self, topic_id: str, paper_id: str, vote: Vote | None) -> None:
        """Record a vote, or clear it with `None`."""
        with self._connection:
            if vote is None:
                self._connection.execute(
                    "DELETE FROM relevance_feedback WHERE topic_id = ? AND paper_id = ?",
                    (topic_id, paper_id),
                )
                return
            self._connection.execute(
                "INSERT INTO relevance_feedback (topic_id, paper_id, vote, updated_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(topic_id, paper_id) DO UPDATE SET "
                "vote = excluded.vote, updated_at = excluded.updated_at",
                (topic_id, paper_id, vote, now_iso()),
            )

    def votes_for(self, topic_id: str, paper_ids: Iterable[str]) -> dict[str, Vote]:
        ids = list(paper_ids)
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        rows = self._connection.execute(
            f"SELECT paper_id, vote FROM relevance_feedback "
            f"WHERE topic_id = ? AND paper_id IN ({placeholders})",
            [topic_id, *ids],
        ).fetchall()
        return {row["paper_id"]: row["vote"] for row in rows}

    def examples(self, topic_id: str, per_side: int) -> FeedbackExamples:
        def titles(vote: int) -> list[str]:
            rows = self._connection.execute(
                "SELECT p.title FROM relevance_feedback f JOIN papers p ON p.id = f.paper_id "
                "WHERE f.topic_id = ? AND f.vote = ? ORDER BY f.updated_at DESC, p.id LIMIT ?",
                (topic_id, vote, per_side),
            ).fetchall()
            return [row["title"] for row in rows]

        return FeedbackExamples(relevant=titles(1), not_relevant=titles(-1))
