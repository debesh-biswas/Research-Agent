import sqlite3

from research_agent.config import TopicSettings
from research_agent.domain.selection import SelectionDecision, SelectionPlan
from research_agent.storage.library import SqliteLibraryRepository
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.reading import ReadingState, SqliteReadingRepository
from research_agent.storage.runs import SqliteRunRepository
from research_agent.storage.selections import SqliteSelectionRepository
from research_agent.storage.topics import SqliteTopicRepository
from tests.unit.conftest import TOPIC_ID, candidate


def _run_keeping(
    connection: sqlite3.Connection, topic: str, kept: list[str], dropped: list[str]
) -> str:
    run = SqliteRunRepository(connection).start(topic)
    decisions = [
        SelectionDecision(
            paper_id=paper_id,
            rank=rank,
            selected=paper_id in kept,
            action="deep_read" if paper_id in kept else "ignore",
            reason="selected_deep_read" if paper_id in kept else "action_ignore",
        )
        for rank, paper_id in enumerate(kept + dropped, start=1)
    ]
    SqliteSelectionRepository(connection).save(run.id, SelectionPlan(decisions=decisions))
    return run.id


def test_each_kept_paper_appears_once_under_its_newest_run(connection: sqlite3.Connection) -> None:
    SqliteTopicRepository(connection).add(TopicSettings(id="other_topic", name="Other"))
    papers = SqlitePaperRepository(connection)
    a, b, c, d = (papers.upsert(candidate(title=t, doi=f"10.1/{t}")) for t in "abcd")
    older = _run_keeping(connection, TOPIC_ID, [a, b], [d])
    newer = _run_keeping(connection, TOPIC_ID, [a], [])
    other = _run_keeping(connection, "other_topic", [c], [])
    SqliteReadingRepository(connection).save(b, ReadingState(read=True, saved=True))
    library = SqliteLibraryRepository(connection)

    total, entries = library.page()
    assert total == 3, "d was only ever dropped"
    assert {entry.paper_id: entry.run_id for entry in entries} == {a: newer, b: older, c: other}

    assert [e.paper_id for e in library.page(saved_only=True)[1]] == [b]
    assert {e.paper_id for e in library.page(unread_only=True)[1]} == {a, c}
    assert {e.paper_id for e in library.page(topic_id="other_topic")[1]} == {c}
    assert library.page(topic_id="other_topic")[1][0].topic_name == "Other"

    first_total, first = library.page(limit=2)
    _, rest = library.page(offset=2, limit=2)
    assert first_total == 3 and len(first) == 2 and len(rest) == 1
    assert {e.paper_id for e in first + rest} == {a, b, c}
