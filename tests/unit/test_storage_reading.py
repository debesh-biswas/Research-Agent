import sqlite3

import pytest
from pydantic import ValidationError

from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.reading import MAX_NOTE_CHARS, ReadingState, SqliteReadingRepository
from tests.unit.conftest import candidate


def test_reading_state_round_trips_and_upserts(connection: sqlite3.Connection) -> None:
    paper_id = SqlitePaperRepository(connection).upsert(candidate(title="Maps", doi="10.1/maps"))
    reading = SqliteReadingRepository(connection)
    assert reading.states_for([]) == {}
    assert reading.states_for([paper_id]) == {}, "no row means unread, unsaved, no note"

    reading.save(paper_id, ReadingState(read=True, note="Check table 3."))
    reading.save(paper_id, ReadingState(read=True, saved=True, note="Check table 3."))

    assert reading.states_for([paper_id, "other"]) == {
        paper_id: ReadingState(read=True, saved=True, note="Check table 3.")
    }


def test_a_note_is_bounded() -> None:
    with pytest.raises(ValidationError):
        ReadingState(note="x" * (MAX_NOTE_CHARS + 1))
