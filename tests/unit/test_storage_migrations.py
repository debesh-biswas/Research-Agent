import sqlite3
from pathlib import Path

import pytest
from conftest import TOPIC_ID

from research_agent.storage.database import MIGRATIONS, apply_migrations, connect


def test_every_required_table_exists(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    names = {row["name"] for row in rows}

    assert {
        "topics",
        "runs",
        "papers",
        "paper_sources",
        "paper_files",
        "classifications",
        "paper_analyses",
        "weekly_syntheses",
        "research_gaps",
        "research_ideas",
        "errors",
        "query_plans",
        "selections",
    } <= names


def test_reapplying_migrations_is_a_no_op(connection: sqlite3.Connection) -> None:
    assert apply_migrations(connection) == len(MIGRATIONS)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


def test_a_version_one_database_upgrades_in_place(tmp_path: Path) -> None:
    legacy = connect(tmp_path / "legacy.db")
    with legacy:
        legacy.execute(MIGRATIONS[0])
        legacy.execute("PRAGMA user_version = 1")
        legacy.execute(
            "INSERT INTO topics VALUES (?, 'Spatial', 1, 10, 'A', NULL, 'weekly', 'sunday', "
            "1, 1, 1, 500, 250, 50, 15, '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00')",
            (TOPIC_ID,),
        )

    assert apply_migrations(legacy) == len(MIGRATIONS)
    assert legacy.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    # The pre-existing topic row survived the upgrade and got the column added later.
    row = legacy.execute("SELECT COUNT(*) AS total, keywords_json FROM topics").fetchone()
    assert (row["total"], row["keywords_json"]) == (1, "[]")
    # Columns added by later migrations exist and start empty.
    columns = {column["name"] for column in legacy.execute("PRAGMA table_info(papers)").fetchall()}
    assert {"content_hash", "analyzed_hash", "first_analyzed_at", "last_analyzed_at"} <= columns
    legacy.close()


def test_foreign_keys_reject_an_orphan_run(connection: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO runs (id, topic_id, started_at, status, active_classifier) "
            "VALUES ('r1', 'missing_topic', '2026-09-22T00:00:00+00:00', 'running', 'A')"
        )


def test_deleting_a_topic_cascades_to_its_runs(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO runs (id, topic_id, started_at, status, active_classifier) "
        "VALUES ('r1', ?, '2026-09-22T00:00:00+00:00', 'running', 'A')",
        (TOPIC_ID,),
    )

    connection.execute("DELETE FROM topics WHERE id = ?", (TOPIC_ID,))

    assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
