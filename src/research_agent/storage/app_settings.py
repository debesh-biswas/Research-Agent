"""Settings changed on the desk's Settings page, kept in the library beside everything else.

Precedence, highest first: process environment, `.env`, these desk changes, `settings.yaml`,
then the model defaults. The YAML file is never rewritten, so its comments survive, and a backup
carries the desk changes with the library.
"""

import json
import logging
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from research_agent.config import ApplicationSettings, _load_yaml_mapping
from research_agent.storage.database import now_iso

_LOGGER = logging.getLogger(__name__)
_NAME = "desk_overrides"
DATABASE_NAME = "research_agent.db"


class SqliteSettingsOverrides:
    """The desk's changes as one nested mapping, e.g. ``{"models": {"local": {"model": "x"}}}``."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get(self) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT payload_json FROM app_settings WHERE name = ?", (_NAME,)
        ).fetchone()
        return dict(json.loads(row["payload_json"])) if row else {}

    def save(self, overrides: Mapping[str, Any]) -> None:
        with self._connection:
            if not overrides:
                self._connection.execute("DELETE FROM app_settings WHERE name = ?", (_NAME,))
                return
            self._connection.execute(
                "INSERT INTO app_settings (name, payload_json, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET payload_json = excluded.payload_json, "
                "updated_at = excluded.updated_at",
                (_NAME, json.dumps(overrides, sort_keys=True), now_iso()),
            )


def merged(base: Mapping[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    """`base` with `changes` laid over it, mapping by mapping."""
    result = dict(base)
    for key, value in changes.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = merged(result[key], value)
        else:
            result[key] = value
    return result


def load_settings(settings_path: Path) -> ApplicationSettings:
    """The settings every command runs with: the YAML file plus the desk's saved changes."""
    file_values = _load_yaml_mapping(settings_path)
    base = ApplicationSettings(**file_values)
    overrides = read_overrides(base.data_directory / DATABASE_NAME)
    if not overrides:
        return base
    try:
        return ApplicationSettings(**merged(file_values, overrides))
    except ValidationError as error:
        # A saved change the current version no longer accepts must not stop every command.
        _LOGGER.warning(
            "ignoring desk settings that no longer validate; reset them on the Settings page",
            extra={"node_name": "settings", "status": "ignored", "error_type": str(error)[:200]},
        )
        return base


def read_overrides(database: Path) -> dict[str, Any]:
    """Read-only, and empty for a library that has none (or no database yet)."""
    if not database.is_file():
        return {}
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    connection.row_factory = sqlite3.Row
    try:
        return SqliteSettingsOverrides(connection).get()
    except sqlite3.OperationalError:  # a library from before this table existed
        return {}
    finally:
        connection.close()
