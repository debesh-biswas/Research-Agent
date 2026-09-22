"""Query plan persistence, so a run's searches can be audited after the fact."""

import sqlite3
import uuid
from typing import Protocol

from research_agent.domain.queries import QueryPlan
from research_agent.storage.database import now_iso


class QueryPlanRepository(Protocol):
    """Storage-neutral repository for resolved search plans."""

    def save(self, plan: QueryPlan, run_id: str | None = None) -> str: ...

    def recent(self, topic_id: str, limit: int = 4) -> list[QueryPlan]: ...


class SqliteQueryPlanRepository:
    """SQLite-backed :class:`QueryPlanRepository`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def save(self, plan: QueryPlan, run_id: str | None = None) -> str:
        """Store one plan and return its id. ``run_id`` is optional, so previews are audited too."""
        plan_id = uuid.uuid4().hex
        with self._connection:
            self._connection.execute(
                "INSERT INTO query_plans (id, run_id, topic_id, created_at, prompt_version, "
                "   model_provider, model_name, fell_back, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    plan_id,
                    run_id,
                    plan.topic_id,
                    now_iso(),
                    plan.prompt_version,
                    plan.model_provider,
                    plan.model_name,
                    int(plan.fell_back),
                    plan.model_dump_json(),
                ),
            )
        return plan_id

    def recent(self, topic_id: str, limit: int = 4) -> list[QueryPlan]:
        """Return the newest plans for a topic, newest first and deterministically ordered."""
        rows = self._connection.execute(
            "SELECT payload_json FROM query_plans WHERE topic_id = ? "
            "ORDER BY created_at DESC, id DESC LIMIT ?",
            (topic_id, limit),
        ).fetchall()
        return [QueryPlan.model_validate_json(row["payload_json"]) for row in rows]
