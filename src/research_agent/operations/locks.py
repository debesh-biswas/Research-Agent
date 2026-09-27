"""Per-topic run locks.

A weekly run is long and writes to one topic's artifacts, so two overlapping runs of the same topic
would fight over the same files. One lock file per topic, created exclusively, is enough for a
single-user local tool.
"""

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


class RunLocked(RuntimeError):
    """Raised when another run of the same topic already holds the lock."""


def lock_path(data_directory: Path, topic_id: str) -> Path:
    return data_directory / "locks" / f"{topic_id}.lock"


@contextmanager
def run_lock(data_directory: Path, topic_id: str) -> Iterator[Path]:
    """Hold the topic's lock for the duration of a run, releasing it however the run ends."""
    path = lock_path(data_directory, topic_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        if not _stale(path):
            raise RunLocked(f"another run of {topic_id} is in progress (lock: {path})") from error
        # ponytail: a stale lock is reclaimed by unlinking it, which races only against another
        # process reclaiming the same stale lock; fcntl locking if that ever matters.
        _LOGGER.warning(
            "reclaiming a stale run lock",
            extra={"topic_id": topic_id, "node_name": "run", "status": "stale_lock"},
        )
        path.unlink(missing_ok=True)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(descriptor, f"{os.getpid()}\n".encode())
        os.close(descriptor)
        yield path
    finally:
        path.unlink(missing_ok=True)


def _stale(path: Path) -> bool:
    """A lock whose process is gone is stale; an unreadable one is treated as held."""
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False
