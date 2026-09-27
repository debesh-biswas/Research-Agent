"""Shared fixtures for the integration tests that drive the graph directly."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from research_agent.config import TopicSettings
from research_agent.storage.database import apply_migrations, connect
from research_agent.storage.topics import SqliteTopicRepository

TOPIC_ID = "spatial_intelligence"


def graph_topic() -> TopicSettings:
    """The topic the graph tests run: OpenAlex only, so one mock transport serves discovery."""
    return TopicSettings.model_validate(
        {
            "id": TOPIC_ID,
            "name": "Spatial Intelligence",
            "keywords": ["embodied navigation", "metric control"],
            "discovery": {"openalex": True, "semantic_scholar": False, "arxiv": False},
        }
    )


@pytest.fixture
def connection(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    """A migrated database seeded with that topic, so foreign keys are satisfiable."""
    database = connect(tmp_path / "agent.db")
    apply_migrations(database)
    SqliteTopicRepository(database).add(graph_topic())
    yield database
    database.close()
