import sqlite3

from research_agent.config import TopicSettings
from research_agent.storage.feedback import SqliteFeedbackRepository
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.topics import SqliteTopicRepository
from tests.unit.conftest import TOPIC_ID, candidate


def test_votes_set_change_clear_and_stay_per_topic(connection: sqlite3.Connection) -> None:
    SqliteTopicRepository(connection).add(TopicSettings(id="other_topic", name="Other"))
    papers = SqlitePaperRepository(connection)
    paper = papers.upsert(candidate(title="Maps", doi="10.1/maps"))
    feedback = SqliteFeedbackRepository(connection)

    feedback.set_vote(TOPIC_ID, paper, 1)
    feedback.set_vote("other_topic", paper, -1)
    assert feedback.votes_for(TOPIC_ID, [paper]) == {paper: 1}
    assert feedback.votes_for("other_topic", [paper]) == {paper: -1}

    feedback.set_vote(TOPIC_ID, paper, -1)
    assert feedback.votes_for(TOPIC_ID, [paper]) == {paper: -1}
    feedback.set_vote(TOPIC_ID, paper, None)
    assert feedback.votes_for(TOPIC_ID, [paper, "unknown"]) == {}
    assert feedback.votes_for(TOPIC_ID, []) == {}


def test_examples_are_newest_first_and_bounded(connection: sqlite3.Connection) -> None:
    papers = SqlitePaperRepository(connection)
    feedback = SqliteFeedbackRepository(connection)
    for index, vote in enumerate((1, 1, 1, -1)):
        paper = papers.upsert(candidate(title=f"Paper {index}", doi=f"10.1/{index}"))
        feedback.set_vote(TOPIC_ID, paper, vote)  # type: ignore[arg-type]

    examples = feedback.examples(TOPIC_ID, per_side=2)

    assert examples.relevant == ["Paper 2", "Paper 1"]
    assert examples.not_relevant == ["Paper 3"]
