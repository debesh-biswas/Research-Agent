"""Classification, analysis, synthesis, gap, and idea persistence.

Each table keeps its lookup columns plus one ``payload_json`` column holding the validated
Pydantic model, so downstream features can extend a schema without a migration.
"""

import json
import sqlite3
import uuid
from datetime import date
from typing import Protocol

from research_agent.domain.analysis import (
    ClassificationResult,
    PaperAnalysis,
    ResearchGap,
    ResearchIdea,
    WeeklySynthesis,
)
from research_agent.storage.database import now_iso


class ResultRepository(Protocol):
    """Storage-neutral repository for model-produced records."""

    def save_classification(
        self,
        run_id: str,
        result: ClassificationResult,
        is_active: bool = True,
        raw_response: object = None,
    ) -> None: ...

    def classifications_for(self, run_id: str) -> list[ClassificationResult]: ...

    def classification_pairs(
        self, topic_id: str, limit: int = 4
    ) -> tuple[list[ClassificationResult], list[ClassificationResult]]: ...

    def save_analysis(self, run_id: str, analysis: PaperAnalysis) -> None: ...

    def analysis_for(self, paper_id: str) -> PaperAnalysis | None: ...

    def save_synthesis(
        self,
        run_id: str,
        topic_id: str,
        synthesis: WeeklySynthesis,
        period_start: date,
        period_end: date,
    ) -> None: ...

    def recent_syntheses(self, topic_id: str, limit: int = 4) -> list[WeeklySynthesis]: ...

    def save_gaps(self, run_id: str, topic_id: str, gaps: list[ResearchGap]) -> None: ...

    def gaps_for(self, run_id: str) -> list[ResearchGap]: ...

    def save_ideas(self, run_id: str, topic_id: str, ideas: list[ResearchIdea]) -> None: ...

    def ideas_for(self, run_id: str) -> list[ResearchIdea]: ...


class SqliteResultRepository:
    """SQLite-backed :class:`ResultRepository`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save_classification(
        self,
        run_id: str,
        result: ClassificationResult,
        is_active: bool = True,
        raw_response: object = None,
    ) -> None:
        """Store one verdict. Shadow results are stored with ``is_active`` false and never route."""
        with self._connection:
            self._connection.execute(
                "INSERT INTO classifications (id, run_id, paper_id, classifier_name, is_active, "
                "   latency_ms, created_at, payload_json, raw_response_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    run_id,
                    result.paper_id,
                    result.classifier_name,
                    int(is_active),
                    result.latency_ms,
                    now_iso(),
                    result.model_dump_json(),
                    None if raw_response is None else json.dumps(raw_response, default=str),
                ),
            )

    def classifications_for(
        self, run_id: str, active_only: bool = False
    ) -> list[ClassificationResult]:
        query = (
            "SELECT payload_json FROM classifications WHERE run_id = ?"
            + (" AND is_active = 1" if active_only else "")
            + " ORDER BY created_at, id"
        )
        rows = self._connection.execute(query, (run_id,)).fetchall()
        return [ClassificationResult.model_validate_json(row["payload_json"]) for row in rows]

    def classification_pairs(
        self, topic_id: str, limit: int = 4
    ) -> tuple[list[ClassificationResult], list[ClassificationResult]]:
        """Active and shadow verdicts from a topic's most recent runs, for comparison."""
        rows = self._connection.execute(
            "SELECT c.is_active, c.payload_json FROM classifications c "
            "JOIN runs r ON r.id = c.run_id WHERE r.topic_id = ? AND r.id IN ("
            "   SELECT id FROM runs WHERE topic_id = ? ORDER BY started_at DESC, id DESC LIMIT ?"
            ") ORDER BY c.created_at, c.id",
            (topic_id, topic_id, limit),
        ).fetchall()
        verdicts = [
            (bool(row["is_active"]), ClassificationResult.model_validate_json(row["payload_json"]))
            for row in rows
        ]
        return (
            [result for is_active, result in verdicts if is_active],
            [result for is_active, result in verdicts if not is_active],
        )

    def save_analysis(self, run_id: str, analysis: PaperAnalysis) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO paper_analyses (id, run_id, paper_id, model_provider, model_name, "
                "   created_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    run_id,
                    analysis.paper_id,
                    analysis.model_provider,
                    analysis.model_name,
                    now_iso(),
                    analysis.model_dump_json(),
                ),
            )

    def analysis_for(self, paper_id: str) -> PaperAnalysis | None:
        """Return the newest analysis of a paper, the cache lookup that avoids a re-read."""
        row = self._connection.execute(
            "SELECT payload_json FROM paper_analyses WHERE paper_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (paper_id,),
        ).fetchone()
        return None if row is None else PaperAnalysis.model_validate_json(row["payload_json"])

    def save_synthesis(
        self,
        run_id: str,
        topic_id: str,
        synthesis: WeeklySynthesis,
        period_start: date,
        period_end: date,
    ) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO weekly_syntheses (id, run_id, topic_id, period_start, period_end, "
                "   created_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    uuid.uuid4().hex,
                    run_id,
                    topic_id,
                    period_start.isoformat(),
                    period_end.isoformat(),
                    now_iso(),
                    synthesis.model_dump_json(),
                ),
            )

    def recent_syntheses(self, topic_id: str, limit: int = 4) -> list[WeeklySynthesis]:
        """Return the newest syntheses first, the history window used for weekly comparison."""
        rows = self._connection.execute(
            "SELECT payload_json FROM weekly_syntheses WHERE topic_id = ? "
            "ORDER BY period_end DESC, created_at DESC, id DESC LIMIT ?",
            (topic_id, limit),
        ).fetchall()
        return [WeeklySynthesis.model_validate_json(row["payload_json"]) for row in rows]

    def save_gaps(self, run_id: str, topic_id: str, gaps: list[ResearchGap]) -> None:
        self._save_many("research_gaps", run_id, topic_id, [gap.model_dump_json() for gap in gaps])

    def gaps_for(self, run_id: str) -> list[ResearchGap]:
        return [
            ResearchGap.model_validate_json(payload)
            for payload in self._payloads("research_gaps", run_id)
        ]

    def save_ideas(self, run_id: str, topic_id: str, ideas: list[ResearchIdea]) -> None:
        self._save_many(
            "research_ideas", run_id, topic_id, [idea.model_dump_json() for idea in ideas]
        )

    def ideas_for(self, run_id: str) -> list[ResearchIdea]:
        return [
            ResearchIdea.model_validate_json(payload)
            for payload in self._payloads("research_ideas", run_id)
        ]

    def _save_many(self, table: str, run_id: str, topic_id: str, payloads: list[str]) -> None:
        # Table names come from this module only; user data is always bound as parameters.
        timestamp = now_iso()
        with self._connection:
            self._connection.executemany(
                f"INSERT INTO {table} (id, run_id, topic_id, created_at, payload_json) "
                "VALUES (?, ?, ?, ?, ?)",
                [(uuid.uuid4().hex, run_id, topic_id, timestamp, payload) for payload in payloads],
            )

    def _payloads(self, table: str, run_id: str) -> list[str]:
        rows = self._connection.execute(
            f"SELECT payload_json FROM {table} WHERE run_id = ? ORDER BY created_at, id", (run_id,)
        ).fetchall()
        return [row["payload_json"] for row in rows]
