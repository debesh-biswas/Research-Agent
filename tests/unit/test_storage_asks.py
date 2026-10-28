import sqlite3

from research_agent.storage.asks import AskTurn, SqliteAskRepository
from research_agent.storage.runs import SqliteRunRepository
from tests.unit.conftest import TOPIC_ID


def test_threads_are_kept_per_run_and_paper_and_go_with_their_run(
    connection: sqlite3.Connection,
) -> None:
    runs = SqliteRunRepository(connection)
    first, second = runs.start(TOPIC_ID), runs.start(TOPIC_ID)
    asks = SqliteAskRepository(connection)
    cite = {"paperId": "p1", "note": ""}
    asks.add(first.id, None, AskTurn(question="Q1", paragraphs=["A1"], cites=[cite]))
    asks.add(first.id, None, AskTurn(question="Q2", paragraphs=["A2"], note="Local."))
    asks.add(first.id, "p1", AskTurn(question="Q3", paragraphs=["A3"]))
    asks.add(second.id, None, AskTurn(question="Q4", paragraphs=["A4"]))

    week = asks.turns(first.id, None)
    assert [(turn.question, turn.paragraphs, turn.note) for turn in week] == [
        ("Q1", ["A1"], ""),
        ("Q2", ["A2"], "Local."),
    ]
    assert week[0].cites == [cite] and week[0].asked_at is not None
    assert [turn.question for turn in asks.turns(first.id, "p1")] == ["Q3"]

    assert asks.clear(first.id, "p1") == 1
    assert asks.turns(first.id, "p1") == []
    assert len(asks.turns(first.id, None)) == 2
    runs.delete(first.id)
    assert asks.turns(first.id, None) == []
    assert [turn.question for turn in asks.turns(second.id, None)] == ["Q4"]
