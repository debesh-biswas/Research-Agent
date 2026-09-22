import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research_agent.config import TopicSettings
from research_agent.domain.papers import PaperCandidate, SourceReference
from research_agent.storage.database import apply_migrations, connect
from research_agent.storage.topics import SqliteTopicRepository

TOPIC_ID = "spatial_intelligence"


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A migrated database seeded with one topic, so foreign keys are satisfiable."""
    database = connect(tmp_path / "agent.db")
    apply_migrations(database)
    SqliteTopicRepository(database).add(
        TopicSettings.model_validate({"id": TOPIC_ID, "name": "Spatial Intelligence"})
    )
    yield database
    database.close()


def candidate(**overrides: object) -> PaperCandidate:
    payload: dict[str, object] = {
        "title": "Embodied Spatial Intelligence for Robots",
        "discovered_at": datetime(2026, 9, 22, tzinfo=UTC),
        "sources": [SourceReference(source="arxiv", source_id="2409.00001")],
    }
    payload.update(overrides)
    return PaperCandidate.model_validate(payload)
