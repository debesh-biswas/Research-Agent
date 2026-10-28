"""Back up and restore the whole library: the SQLite database and every artifact under topics/.

A backup is one zip file. The database is copied with SQLite's online backup API, so the copy is
consistent even while the desk is reading it. A restore never deletes anything: an existing
library is moved aside, and an archive is checked in full before a single file is written.
"""

import json
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from research_agent import __version__
from research_agent.operations.locks import RunLocked, lock_path, run_lock

DATABASE_NAME = "research_agent.db"
MANIFEST_NAME = "backup.json"
_KIND = "research-agent-backup"


class BackupError(RuntimeError):
    """A backup or restore that was refused, with the reason a person can act on."""


def create_backup(data_directory: Path, output: Path) -> Path:
    """Write the library to `output` (a .zip). Refused while any run is in progress."""
    database = data_directory / DATABASE_NAME
    if not database.is_file():
        raise BackupError(f"there is no library to back up at {data_directory}")
    _refuse_while_running(data_directory, "back up")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as scratch:
        snapshot = Path(scratch) / DATABASE_NAME
        source = sqlite3.connect(database)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        manifest = {
            "kind": _KIND,
            "app_version": __version__,
            "created_at": _now(),
            # The library records absolute file paths; a restore elsewhere rewrites this prefix.
            "data_directory": str(data_directory.resolve()),
        }
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
            archive.write(snapshot, DATABASE_NAME)
            topics = data_directory / "topics"
            for path in sorted(topics.rglob("*")) if topics.is_dir() else []:
                if path.is_file():
                    archive.write(path, path.relative_to(data_directory).as_posix())
    return output


def restore_backup(archive_path: Path, data_directory: Path) -> Path | None:
    """Replace the library with an archive's contents; returns where the old library was moved."""
    names = _validated_names(archive_path)
    _refuse_while_running(data_directory, "restore")
    data_directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=data_directory.parent) as scratch:
        staged = Path(scratch) / "library"
        with zipfile.ZipFile(archive_path) as archive:
            for name in names:
                if name != MANIFEST_NAME:
                    archive.extract(name, staged)
            origin = json.loads(archive.read(MANIFEST_NAME)).get("data_directory")
        if origin:
            _relocate_file_paths(staged / DATABASE_NAME, origin, str(data_directory.resolve()))
        moved = None
        if data_directory.exists() and any(data_directory.iterdir()):
            moved = data_directory.with_name(f"{data_directory.name}.before-restore-{_stamp()}")
            data_directory.rename(moved)
        elif data_directory.exists():
            data_directory.rmdir()
        staged.rename(data_directory)
    return moved


def _relocate_file_paths(database: Path, old_root: str, new_root: str) -> None:
    """Point recorded PDF and parse paths at the restored library rather than the original."""
    if old_root == new_root:
        return
    connection = sqlite3.connect(database)
    try:
        with connection:
            connection.execute(
                "UPDATE paper_files SET path = ? || substr(path, ?) WHERE substr(path, 1, ?) = ?",
                (new_root, len(old_root) + 1, len(old_root) + 1, old_root + "/"),
            )
    finally:
        connection.close()


def library_exists(data_directory: Path) -> bool:
    return (data_directory / DATABASE_NAME).is_file()


def _validated_names(archive_path: Path) -> list[str]:
    """Every member, after proving the file is a backup and no member escapes the library."""
    if not zipfile.is_zipfile(archive_path):
        raise BackupError(f"{archive_path} is not a backup file")
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if MANIFEST_NAME not in names or DATABASE_NAME not in names:
            raise BackupError(f"{archive_path} is not a Research Agent backup")
        manifest = json.loads(archive.read(MANIFEST_NAME))
        if manifest.get("kind") != _KIND:
            raise BackupError(f"{archive_path} is not a Research Agent backup")
    for name in names:
        parts = PurePosixPath(name).parts
        if (
            name.startswith("/")
            or ".." in parts
            or (name not in (MANIFEST_NAME, DATABASE_NAME) and parts[:1] != ("topics",))
        ):
            raise BackupError(f"{archive_path} contains an unsafe path: {name!r}")
    return names


def _refuse_while_running(data_directory: Path, action: str) -> None:
    """A run writes into the library for minutes; copying or moving it then would tear it."""
    locks = data_directory / "locks"
    busy = (
        sorted(path.stem for path in locks.glob("*.lock") if _is_running(data_directory, path.stem))
        if locks.is_dir()
        else []
    )
    if busy:
        raise BackupError(f"a run is in progress ({', '.join(busy)}); {action} after it finishes")


def _is_running(data_directory: Path, topic_id: str) -> bool:
    if not lock_path(data_directory, topic_id).exists():
        return False
    try:
        with run_lock(data_directory, topic_id):
            return False
    except RunLocked:
        return True


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
