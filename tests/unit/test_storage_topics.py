from pathlib import Path

import pytest
import yaml

from research_agent.config import TopicSettings
from research_agent.storage.database import MIGRATIONS, apply_migrations, connect
from research_agent.storage.topics import (
    DuplicateTopicError,
    SqliteTopicRepository,
    TopicNotFoundError,
    bootstrap,
)


def _repository(path: Path) -> SqliteTopicRepository:
    connection = connect(path)
    apply_migrations(connection)
    return SqliteTopicRepository(connection)


def _topic(topic_id: str = "spatial_intelligence", **overrides: object) -> TopicSettings:
    payload: dict[str, object] = {"id": topic_id, "name": topic_id.replace("_", " ").title()}
    payload.update(overrides)
    return TopicSettings.model_validate(payload)


def test_migrations_are_idempotent(tmp_path: Path) -> None:
    connection = connect(tmp_path / "nested" / "agent.db")

    assert apply_migrations(connection) == len(MIGRATIONS)
    assert apply_migrations(connection) == len(MIGRATIONS)

    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'topics'"
    ).fetchall()
    assert len(tables) == 1


def test_add_round_trips_every_field(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "agent.db")
    topic = _topic(
        enabled=False,
        lookback_days=21,
        classifier={"active": "B", "shadow": None},
        discovery={"openalex": False, "semantic_scholar": True, "arxiv": False},
        limits={
            "max_candidates": 40,
            "max_classified": 30,
            "max_downloads": 20,
            "max_deep_reads": 10,
        },
        scheduling={"frequency": "weekly", "day": "monday"},
    )

    repository.add(topic)

    assert repository.get(topic.id) == topic
    assert repository.list() == [topic]


def test_get_returns_none_for_unknown_topic(tmp_path: Path) -> None:
    assert _repository(tmp_path / "agent.db").get("missing") is None


def test_duplicate_id_is_rejected_and_leaves_original(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "agent.db")
    repository.add(_topic())

    with pytest.raises(DuplicateTopicError):
        repository.add(_topic(name="Replacement"))

    stored = repository.list()
    assert len(stored) == 1
    assert stored[0].name == "Spatial Intelligence"


def test_set_enabled_toggles_and_rejects_unknown_topic(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "agent.db")
    repository.add(_topic())

    repository.set_enabled("spatial_intelligence", False)
    stored = repository.get("spatial_intelligence")
    assert stored is not None and stored.enabled is False

    repository.set_enabled("spatial_intelligence", True)
    stored = repository.get("spatial_intelligence")
    assert stored is not None and stored.enabled is True

    with pytest.raises(TopicNotFoundError):
        repository.set_enabled("missing", False)


def test_list_orders_by_id_regardless_of_insertion_order(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "agent.db")
    for topic_id in ("zeta_topic", "alpha_topic", "mid_topic"):
        repository.add(_topic(topic_id))

    assert [topic.id for topic in repository.list()] == ["alpha_topic", "mid_topic", "zeta_topic"]


def test_topics_survive_a_new_connection(tmp_path: Path) -> None:
    database = tmp_path / "agent.db"
    _repository(database).add(_topic())

    assert [topic.id for topic in _repository(database).list()] == ["spatial_intelligence"]


def test_bootstrap_seeds_once(tmp_path: Path) -> None:
    topics_path = tmp_path / "topics.yaml"
    topics_path.write_text(
        yaml.safe_dump({"topics": [{"id": "seeded_topic", "name": "Seeded"}]}),
        encoding="utf-8",
    )
    repository = _repository(tmp_path / "agent.db")

    assert bootstrap(repository, topics_path) == 1
    assert bootstrap(repository, topics_path) == 0
    assert [topic.id for topic in repository.list()] == ["seeded_topic"]


def test_bootstrap_tolerates_missing_or_invalid_yaml(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "agent.db")
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("topics: []\n", encoding="utf-8")

    assert bootstrap(repository, tmp_path / "missing.yaml") == 0
    assert bootstrap(repository, invalid) == 0
    assert repository.list() == []


def test_keywords_round_trip(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "agent.db")
    repository.add(
        TopicSettings.model_validate(
            {"id": "keyworded", "name": "Keyworded", "keywords": ["spatial reasoning", "slam"]}
        )
    )

    stored = repository.get("keyworded")

    assert stored is not None
    assert stored.keywords == ["spatial reasoning", "slam"]


def test_a_topic_without_keywords_reads_back_empty(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "agent.db")
    repository.add(TopicSettings.model_validate({"id": "bare", "name": "Bare"}))

    stored = repository.get("bare")

    assert stored is not None
    assert stored.keywords == []
