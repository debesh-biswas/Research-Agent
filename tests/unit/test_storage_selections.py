import sqlite3

import pytest
from conftest import TOPIC_ID, candidate

from research_agent.domain.selection import SelectionDecision, SelectionPlan
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.runs import SqliteRunRepository
from research_agent.storage.selections import SqliteSelectionRepository


def _context(connection: sqlite3.Connection) -> tuple[SqliteSelectionRepository, str, str]:
    run = SqliteRunRepository(connection).start(TOPIC_ID)
    paper_id = SqlitePaperRepository(connection).upsert(candidate(doi="10.1234/abcd"))
    return SqliteSelectionRepository(connection), run.id, paper_id


def _plan(paper_id: str, **overrides: object) -> SelectionPlan:
    payload: dict[str, object] = {
        "paper_id": paper_id,
        "rank": 1,
        "selected": True,
        "action": "deep_read",
        "reason": "selected_deep_read",
    }
    payload.update(overrides)
    return SelectionPlan(decisions=[SelectionDecision.model_validate(payload)])


def test_decisions_round_trip(connection: sqlite3.Connection) -> None:
    repository, run_id, paper_id = _context(connection)
    plan = _plan(paper_id)

    repository.save(run_id, plan)

    assert repository.decisions_for(run_id) == plan.decisions
    assert repository.selected_for(run_id) == [paper_id]


def test_a_skipped_paper_keeps_its_reason(connection: sqlite3.Connection) -> None:
    repository, run_id, paper_id = _context(connection)

    repository.save(run_id, _plan(paper_id, selected=False, reason="limit_reached"))

    (decision,) = repository.decisions_for(run_id)
    assert (decision.selected, decision.reason) == (False, "limit_reached")
    assert repository.selected_for(run_id) == []


def test_decisions_are_returned_in_rank_order(connection: sqlite3.Connection) -> None:
    repository, run_id, first = _context(connection)
    second = SqlitePaperRepository(connection).upsert(candidate(doi="10.1234/efgh"))
    plan = SelectionPlan(
        decisions=[
            SelectionDecision(
                paper_id=second,
                rank=2,
                selected=True,
                action="summarize",
                reason="selected_summarize",
            ),
            SelectionDecision(
                paper_id=first,
                rank=1,
                selected=True,
                action="deep_read",
                reason="selected_deep_read",
            ),
        ]
    )

    repository.save(run_id, plan)

    assert [decision.rank for decision in repository.decisions_for(run_id)] == [1, 2]
    assert repository.selected_for(run_id) == [first, second]


def test_one_paper_cannot_be_decided_twice_in_a_run(connection: sqlite3.Connection) -> None:
    repository, run_id, paper_id = _context(connection)
    repository.save(run_id, _plan(paper_id))

    with pytest.raises(sqlite3.IntegrityError):
        repository.save(run_id, _plan(paper_id, rank=2))


def test_a_decision_for_an_unknown_run_is_rejected(connection: sqlite3.Connection) -> None:
    repository, _, paper_id = _context(connection)

    with pytest.raises(sqlite3.IntegrityError):
        repository.save("not_a_run", _plan(paper_id))
