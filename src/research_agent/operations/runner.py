"""Execute one topic's weekly run end to end, reporting how it ended.

The graph already tolerates stage failures; this layer is about what an operator needs: one lock per
topic, a concise outcome, and a non-zero exit only when a run produced nothing.
"""

import asyncio
import logging
import sqlite3
from datetime import UTC, date, datetime, timedelta

from pydantic import Field

from research_agent.config import ApplicationSettings, StrictModel, TopicSettings
from research_agent.domain.runs import RunSummary
from research_agent.operations.locks import RunLocked, run_lock
from research_agent.operations.wiring import ClientFactory, default_client, services_for
from research_agent.storage.runs import SqliteRunRepository
from research_agent.workflow.graph import run_workflow

_LOGGER = logging.getLogger(__name__)

RunConclusion = str


class RunOutcome(StrictModel):
    """How one topic's run ended, in the terms an operator cares about."""

    topic_id: str = Field(min_length=1)
    conclusion: RunConclusion
    """`completed`, `degraded`, `failed`, `skipped` (disabled) or `locked`."""

    run_id: str | None = None
    report_path: str | None = None
    papers_analyzed: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    reason: str | None = None

    @property
    def fatal(self) -> bool:
        """Only a run that produced nothing is fatal; a degraded run still delivered a report."""
        return self.conclusion == "failed"


def reporting_period(topic: TopicSettings, today: date | None = None) -> tuple[date, date]:
    end = today or datetime.now(UTC).date()
    return end - timedelta(days=topic.lookback_days), end


async def execute_run(
    connection: sqlite3.Connection,
    application: ApplicationSettings,
    topic: TopicSettings,
    client_factory: ClientFactory = default_client,
    parser: object | None = None,
    today: date | None = None,
) -> RunOutcome:
    """Run one topic under its lock. Interruption still closes the run and keeps its artifacts."""
    if not topic.enabled:
        return RunOutcome(topic_id=topic.id, conclusion="skipped", reason="the topic is disabled")

    start, end = reporting_period(topic, today)
    try:
        with run_lock(application.data_directory, topic.id):
            async with services_for(connection, application, topic, client_factory, parser) as (
                services
            ):
                state = await run_workflow(services, start, end)
    except RunLocked as error:
        return RunOutcome(topic_id=topic.id, conclusion="locked", reason=str(error))
    # Interruption is caught around the whole run, including service teardown, because Ctrl-C can
    # arrive as a cancellation from inside the graph rather than as KeyboardInterrupt here.
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError) as interruption:
        return _interrupted(connection, topic, interruption)

    return RunOutcome(
        topic_id=topic.id,
        conclusion=state.status,
        run_id=state.run_id,
        report_path=state.report_path,
        papers_analyzed=len(state.analyzed_ids),
        errors=len(state.errors),
    )


def _interrupted(
    connection: sqlite3.Connection, topic: TopicSettings, interruption: BaseException
) -> RunOutcome:
    """Mark the newest open run failed so an interrupted run is never left reading as running."""
    runs = SqliteRunRepository(connection)
    recent = runs.recent(topic.id, limit=1)
    run_id = None
    if recent and recent[0].status == "running":
        run_id = recent[0].id
        runs.complete(run_id, recent[0].summary or RunSummary(), status="failed")
    _LOGGER.warning(
        "run interrupted",
        extra={"topic_id": topic.id, "run_id": run_id, "node_name": "run", "status": "interrupted"},
    )
    return RunOutcome(
        topic_id=topic.id,
        conclusion="failed",
        run_id=run_id,
        reason=f"interrupted: {type(interruption).__name__}",
    )
