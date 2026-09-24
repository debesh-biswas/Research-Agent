import sqlite3
from datetime import UTC, datetime

import pytest

from research_agent.domain.queries import QueryPlan
from research_agent.storage.queries import SqliteQueryPlanRepository
from research_agent.storage.runs import SqliteRunRepository
from tests.unit.conftest import TOPIC_ID


def make_plan(**overrides: object) -> QueryPlan:
    payload: dict[str, object] = {
        "topic_id": TOPIC_ID,
        "queries": ["spatial intelligence", "embodied navigation"],
        "base_query": "spatial intelligence",
        "prompt_version": "query_expansion.v1",
        "model_provider": "local",
        "model_name": "qwen3:8b",
        "created_at": datetime(2026, 9, 22, tzinfo=UTC),
    }
    payload.update(overrides)
    return QueryPlan.model_validate(payload)


def test_a_plan_round_trips_without_a_run(connection: sqlite3.Connection) -> None:
    repository = SqliteQueryPlanRepository(connection)
    plan = make_plan()

    plan_id = repository.save(plan)

    assert plan_id
    assert repository.recent(TOPIC_ID) == [plan]


def test_a_plan_can_be_attached_to_a_run(connection: sqlite3.Connection) -> None:
    run = SqliteRunRepository(connection).start(TOPIC_ID, "A")
    repository = SqliteQueryPlanRepository(connection)

    repository.save(make_plan(), run_id=run.id)

    row = connection.execute("SELECT run_id, fell_back, model_name FROM query_plans").fetchone()
    assert row["run_id"] == run.id
    assert row["fell_back"] == 0
    assert row["model_name"] == "qwen3:8b"


def test_a_fallback_plan_records_its_missing_provenance(connection: sqlite3.Connection) -> None:
    repository = SqliteQueryPlanRepository(connection)

    repository.save(make_plan(model_provider=None, model_name=None, fell_back=True))

    row = connection.execute("SELECT fell_back, model_provider FROM query_plans").fetchone()
    assert (row["fell_back"], row["model_provider"]) == (1, None)


def test_recent_returns_the_newest_plans_first(connection: sqlite3.Connection) -> None:
    repository = SqliteQueryPlanRepository(connection)
    for index in range(3):
        repository.save(make_plan(base_query=f"query {index}", queries=[f"query {index}"]))

    recent = repository.recent(TOPIC_ID, limit=2)

    assert len(recent) == 2
    assert {plan.base_query for plan in recent} <= {"query 0", "query 1", "query 2"}


def test_a_plan_for_an_unknown_topic_is_rejected(connection: sqlite3.Connection) -> None:
    repository = SqliteQueryPlanRepository(connection)

    with pytest.raises(sqlite3.IntegrityError):
        repository.save(make_plan(topic_id="not_a_topic"))
