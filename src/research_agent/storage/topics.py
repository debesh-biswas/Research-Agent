"""Topic persistence behind a repository interface."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from research_agent.config import (
    ConfigurationError,
    TopicsConfiguration,
    TopicSettings,
    _load_yaml_mapping,
)

_COLUMNS = (
    "id, name, enabled, lookback_days, active_classifier, shadow_classifier, "
    "schedule_frequency, schedule_day, source_openalex, source_semantic_scholar, "
    "source_arxiv, max_candidates, max_classified, max_downloads, max_deep_reads, "
    "keywords_json"
)


class TopicStoreError(Exception):
    """Base class for recoverable topic persistence failures."""


class DuplicateTopicError(TopicStoreError):
    """Raised when a topic id already exists."""


class TopicNotFoundError(TopicStoreError):
    """Raised when a topic id does not exist."""


class TopicRepository(Protocol):
    """Storage-neutral topic repository."""

    def add(self, topic: TopicSettings) -> None: ...

    def get(self, topic_id: str) -> TopicSettings | None: ...

    def list(self) -> list[TopicSettings]: ...

    def set_enabled(self, topic_id: str, enabled: bool) -> None: ...


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _to_row(topic: TopicSettings) -> dict[str, Any]:
    return {
        "id": topic.id,
        "name": topic.name,
        "enabled": int(topic.enabled),
        "lookback_days": topic.lookback_days,
        "keywords_json": json.dumps(topic.keywords),
        "active_classifier": topic.classifier.active,
        "shadow_classifier": topic.classifier.shadow,
        "schedule_frequency": topic.scheduling.frequency,
        "schedule_day": topic.scheduling.day,
        "source_openalex": int(topic.discovery.openalex),
        "source_semantic_scholar": int(topic.discovery.semantic_scholar),
        "source_arxiv": int(topic.discovery.arxiv),
        "max_candidates": topic.limits.max_candidates,
        "max_classified": topic.limits.max_classified,
        "max_downloads": topic.limits.max_downloads,
        "max_deep_reads": topic.limits.max_deep_reads,
    }


def _from_row(row: sqlite3.Row) -> TopicSettings:
    return TopicSettings.model_validate(
        {
            "id": row["id"],
            "name": row["name"],
            "enabled": bool(row["enabled"]),
            "lookback_days": row["lookback_days"],
            "keywords": json.loads(row["keywords_json"]),
            "classifier": {
                "active": row["active_classifier"],
                "shadow": row["shadow_classifier"],
            },
            "discovery": {
                "openalex": bool(row["source_openalex"]),
                "semantic_scholar": bool(row["source_semantic_scholar"]),
                "arxiv": bool(row["source_arxiv"]),
            },
            "limits": {
                "max_candidates": row["max_candidates"],
                "max_classified": row["max_classified"],
                "max_downloads": row["max_downloads"],
                "max_deep_reads": row["max_deep_reads"],
            },
            "scheduling": {
                "frequency": row["schedule_frequency"],
                "day": row["schedule_day"],
            },
        }
    )


class SqliteTopicRepository:
    """SQLite-backed :class:`TopicRepository`."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def add(self, topic: TopicSettings) -> None:
        values = _to_row(topic)
        values["created_at"] = values["updated_at"] = _now()
        placeholders = ", ".join(f":{column}" for column in values)
        try:
            with self._connection:
                self._connection.execute(
                    f"INSERT INTO topics ({', '.join(values)}) VALUES ({placeholders})",
                    values,
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateTopicError(f"topic already exists: {topic.id}") from error

    def get(self, topic_id: str) -> TopicSettings | None:
        row = self._connection.execute(
            f"SELECT {_COLUMNS} FROM topics WHERE id = ?", (topic_id,)
        ).fetchone()
        return None if row is None else _from_row(row)

    def list(self) -> list[TopicSettings]:
        rows = self._connection.execute(f"SELECT {_COLUMNS} FROM topics ORDER BY id").fetchall()
        return [_from_row(row) for row in rows]

    def set_enabled(self, topic_id: str, enabled: bool) -> None:
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE topics SET enabled = ?, updated_at = ? WHERE id = ?",
                (int(enabled), _now(), topic_id),
            )
        if cursor.rowcount == 0:
            raise TopicNotFoundError(f"unknown topic: {topic_id}")


def bootstrap(repository: TopicRepository, topics_path: Path) -> int:
    """Seed an empty repository from the topics YAML and return how many were added.

    A missing or invalid YAML file leaves the repository empty rather than failing, so topic
    commands still work before any configuration exists.
    """
    if repository.list():
        return 0
    try:
        configuration = TopicsConfiguration.model_validate(_load_yaml_mapping(topics_path))
    except (ConfigurationError, ValidationError):
        return 0
    for topic in configuration.topics:
        repository.add(topic)
    return len(configuration.topics)
