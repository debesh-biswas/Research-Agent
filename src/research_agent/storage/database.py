"""SQLite connection and migration foundation."""

import sqlite3
from datetime import UTC, datetime
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
    """
    CREATE TABLE runs (
        id TEXT PRIMARY KEY,
        topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        status TEXT NOT NULL,
        papers_found INTEGER NOT NULL DEFAULT 0,
        papers_selected INTEGER NOT NULL DEFAULT 0,
        active_classifier TEXT NOT NULL,
        shadow_classifier TEXT,
        duration_seconds REAL,
        summary_json TEXT
    )
    """,
    """
    CREATE TABLE papers (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        abstract TEXT,
        doi TEXT,
        arxiv_id TEXT,
        publication_date TEXT,
        venue TEXT,
        citation_count INTEGER,
        authors_json TEXT NOT NULL,
        first_seen_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE paper_sources (
        paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        source TEXT NOT NULL,
        source_id TEXT NOT NULL,
        url TEXT,
        pdf_url TEXT,
        PRIMARY KEY (paper_id, source, source_id)
    )
    """,
    """
    CREATE TABLE paper_files (
        id TEXT PRIMARY KEY,
        paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
        kind TEXT NOT NULL,
        path TEXT NOT NULL,
        byte_size INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (paper_id, kind)
    )
    """,
    """
    CREATE TABLE classifications (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        classifier_name TEXT NOT NULL,
        is_active INTEGER NOT NULL,
        latency_ms INTEGER,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        raw_response_json TEXT
    )
    """,
    """
    CREATE TABLE paper_analyses (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        model_provider TEXT NOT NULL,
        model_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE weekly_syntheses (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
        period_start TEXT NOT NULL,
        period_end TEXT NOT NULL,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE research_gaps (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE research_ideas (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE errors (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        paper_id TEXT,
        node TEXT NOT NULL,
        category TEXT NOT NULL,
        recoverable INTEGER NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX papers_doi_idx ON papers(doi)",
    "CREATE INDEX papers_arxiv_idx ON papers(arxiv_id)",
    "CREATE INDEX runs_topic_idx ON runs(topic_id, started_at)",
    "CREATE INDEX syntheses_topic_idx ON weekly_syntheses(topic_id, created_at)",
    "ALTER TABLE topics ADD COLUMN keywords_json TEXT NOT NULL DEFAULT '[]'",
    """
    CREATE TABLE query_plans (
        id TEXT PRIMARY KEY,
        run_id TEXT REFERENCES runs(id) ON DELETE CASCADE,
        topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        model_provider TEXT,
        model_name TEXT,
        fell_back INTEGER NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    "CREATE INDEX query_plans_topic_idx ON query_plans(topic_id, created_at)",
    "ALTER TABLE papers ADD COLUMN content_hash TEXT",
    "ALTER TABLE papers ADD COLUMN first_analyzed_at TEXT",
    "ALTER TABLE papers ADD COLUMN last_analyzed_at TEXT",
    "ALTER TABLE papers ADD COLUMN analyzed_hash TEXT",
    """
    CREATE TABLE selections (
        id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
        paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
        rank INTEGER NOT NULL,
        selected INTEGER NOT NULL,
        action TEXT NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (run_id, paper_id)
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


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string, the format every table stores."""
    return datetime.now(UTC).isoformat()
