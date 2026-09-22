"""SQLite connection and migration foundation."""

import sqlite3
from pathlib import Path

MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE topics (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        enabled INTEGER NOT NULL,
        lookback_days INTEGER NOT NULL,
        active_classifier TEXT NOT NULL,
        shadow_classifier TEXT,
        schedule_frequency TEXT NOT NULL,
        schedule_day TEXT NOT NULL,
        source_openalex INTEGER NOT NULL,
        source_semantic_scholar INTEGER NOT NULL,
        source_arxiv INTEGER NOT NULL,
        max_candidates INTEGER NOT NULL,
        max_classified INTEGER NOT NULL,
        max_downloads INTEGER NOT NULL,
        max_deep_reads INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)


def connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite database, creating its parent directory when needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def apply_migrations(connection: sqlite3.Connection) -> int:
    """Apply pending migrations and return the resulting schema version."""
    current: int = connection.execute("PRAGMA user_version").fetchone()[0]
    if current >= len(MIGRATIONS):
        return current

    with connection:
        for statement in MIGRATIONS[current:]:
            connection.execute(statement)
        # PRAGMA does not accept bound parameters; the value is a trusted int.
        connection.execute(f"PRAGMA user_version = {len(MIGRATIONS)}")
    return len(MIGRATIONS)
