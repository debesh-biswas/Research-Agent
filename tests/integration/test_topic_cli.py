from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner, Result

from research_agent.cli import app
from research_agent.operations.locks import lock_path
from research_agent.storage.database import connect
from research_agent.storage.topics import SqliteTopicRepository

runner = CliRunner()


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump({"data_directory": str(tmp_path / "data")}), encoding="utf-8")
    return path


@pytest.fixture
def topics_path(tmp_path: Path) -> Path:
    path = tmp_path / "topics.yaml"
    path.write_text(
        yaml.safe_dump({"topics": [{"id": "seeded_topic", "name": "Seeded Topic"}]}),
        encoding="utf-8",
    )
    return path


def _invoke(settings: Path, topics: Path, *arguments: str) -> Result:
    return runner.invoke(
        app,
        ["topic", *arguments, "--settings", str(settings), "--topics", str(topics)],
    )


def test_add_then_list_shows_topic(settings_path: Path, topics_path: Path) -> None:
    added = _invoke(settings_path, topics_path, "add", "--id", "new_topic", "--name", "New Topic")
    assert added.exit_code == 0

    listed = _invoke(settings_path, topics_path, "list")
    assert listed.exit_code == 0
    assert "new_topic\tenabled\t10d" in listed.stdout
    assert "New Topic" in listed.stdout


def test_first_list_auto_seeds_from_yaml(settings_path: Path, topics_path: Path) -> None:
    result = _invoke(settings_path, topics_path, "list")

    assert result.exit_code == 0
    assert "seeded_topic" in result.stdout


def test_list_reports_empty_store(settings_path: Path, tmp_path: Path) -> None:
    result = _invoke(settings_path, tmp_path / "missing.yaml", "list")

    assert result.exit_code == 0
    assert "No topics stored" in result.stdout


def test_duplicate_id_is_rejected(settings_path: Path, topics_path: Path) -> None:
    result = _invoke(
        settings_path, topics_path, "add", "--id", "seeded_topic", "--name", "Duplicate"
    )

    assert result.exit_code == 1
    assert "topic already exists: seeded_topic" in result.stderr


def test_all_sources_disabled_is_rejected(settings_path: Path, topics_path: Path) -> None:
    result = _invoke(
        settings_path,
        topics_path,
        "add",
        "--id",
        "bad_topic",
        "--name",
        "Bad Topic",
        "--no-openalex",
        "--no-semantic-scholar",
        "--no-arxiv",
    )

    assert result.exit_code == 1
    assert "at least one discovery source" in result.stderr


def test_missing_settings_file_is_reported(tmp_path: Path, topics_path: Path) -> None:
    result = _invoke(tmp_path / "missing.yaml", topics_path, "list")

    assert result.exit_code == 1
    assert "configuration file not found" in result.stderr


def test_disable_and_enable_change_reported_state(settings_path: Path, topics_path: Path) -> None:
    assert _invoke(settings_path, topics_path, "disable", "seeded_topic").exit_code == 0
    assert "seeded_topic\tdisabled" in _invoke(settings_path, topics_path, "list").stdout

    assert _invoke(settings_path, topics_path, "enable", "seeded_topic").exit_code == 0
    assert "seeded_topic\tenabled" in _invoke(settings_path, topics_path, "list").stdout


def test_enable_unknown_topic_fails(settings_path: Path, topics_path: Path) -> None:
    result = _invoke(settings_path, topics_path, "enable", "missing_topic")

    assert result.exit_code == 1
    assert "unknown topic: missing_topic" in result.stderr


def test_edit_changes_only_the_given_options(
    settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = _invoke(
        settings_path,
        topics_path,
        "edit",
        "seeded_topic",
        "--lookback-days",
        "7",
        "--keyword",
        "slam",
        "--no-semantic-scholar",
    )

    assert result.exit_code == 0, result.stderr
    connection = connect(tmp_path / "data" / "research_agent.db")
    stored = SqliteTopicRepository(connection).get("seeded_topic")
    connection.close()
    assert stored is not None
    assert (stored.name, stored.lookback_days, stored.keywords) == ("Seeded Topic", 7, ["slam"])
    assert (stored.discovery.semantic_scholar, stored.discovery.arxiv) == (False, True)


def test_edit_rejects_invalid_limits_and_unknown_topics(
    settings_path: Path, topics_path: Path
) -> None:
    invalid = _invoke(settings_path, topics_path, "edit", "seeded_topic", "--max-deep-reads", "99")
    missing = _invoke(settings_path, topics_path, "edit", "missing_topic", "--name", "X")

    assert invalid.exit_code == 1 and "max_deep_reads cannot exceed" in invalid.stderr
    assert missing.exit_code == 1 and "unknown topic: missing_topic" in missing.stderr


def test_a_deleted_last_topic_stays_deleted(settings_path: Path, topics_path: Path) -> None:
    deleted = _invoke(settings_path, topics_path, "delete", "seeded_topic", "--yes")

    assert deleted.exit_code == 0, deleted.stderr
    assert "No topics stored" in _invoke(settings_path, topics_path, "list").stdout


def test_delete_asks_first_and_refuses_during_a_run(
    settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    declined = runner.invoke(
        app,
        [
            "topic",
            "delete",
            "seeded_topic",
            "--settings",
            str(settings_path),
            "--topics",
            str(topics_path),
        ],
        input="n\n",
    )
    assert declined.exit_code == 1
    assert "seeded_topic" in _invoke(settings_path, topics_path, "list").stdout

    lock = lock_path(tmp_path / "data", "seeded_topic")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("not a pid", encoding="utf-8")
    locked = _invoke(settings_path, topics_path, "delete", "seeded_topic", "--yes")

    assert locked.exit_code == 1 and "in progress" in locked.stderr
    assert "seeded_topic" in _invoke(settings_path, topics_path, "list").stdout
