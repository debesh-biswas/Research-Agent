"""Local artifact storage behind a path-safe interface."""

import os
import re
import tempfile
from pathlib import Path
from typing import Literal, Protocol

ArtifactKind = Literal["papers", "parsed", "analyses", "reports", "runs"]

_UNSAFE = re.compile(r"[^a-z0-9._-]+")


class ArtifactPathError(ValueError):
    """Raised when a topic or artifact name cannot be mapped to a safe path."""


def safe_name(value: str) -> str:
    """Reduce an identifier to a deterministic, filename-safe token."""
    cleaned = _UNSAFE.sub("_", value.casefold()).strip("._-")
    if not cleaned:
        raise ArtifactPathError(f"unusable artifact name: {value!r}")
    return cleaned


class ArtifactStore(Protocol):
    """Storage-neutral artifact store; implementations may be local or object storage."""

    def path_for(self, topic_id: str, kind: ArtifactKind, name: str) -> Path: ...

    def write_bytes(self, topic_id: str, kind: ArtifactKind, name: str, data: bytes) -> Path: ...

    def write_text(self, topic_id: str, kind: ArtifactKind, name: str, text: str) -> Path: ...

    def read_text(self, topic_id: str, kind: ArtifactKind, name: str) -> str: ...

    def exists(self, topic_id: str, kind: ArtifactKind, name: str) -> bool: ...

    def delete(self, topic_id: str, kind: ArtifactKind, name: str) -> None: ...


class LocalArtifactStore:
    """Filesystem :class:`ArtifactStore` rooted at ``<root>/topics/<topic_id>/<kind>/``."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path_for(self, topic_id: str, kind: ArtifactKind, name: str) -> Path:
        """Resolve a safe path inside the topic directory, rejecting anything that escapes it."""
        topic_root = (self._root / "topics" / safe_name(topic_id) / kind).resolve()
        candidate = (topic_root / safe_name(name)).resolve()
        if not candidate.is_relative_to(topic_root):
            raise ArtifactPathError(f"artifact path escapes its topic directory: {name!r}")
        return candidate

    def write_bytes(self, topic_id: str, kind: ArtifactKind, name: str, data: bytes) -> Path:
        """Write atomically so a crash never leaves a partial artifact behind."""
        path = self.path_for(topic_id, kind, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(data)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return path

    def write_text(self, topic_id: str, kind: ArtifactKind, name: str, text: str) -> Path:
        return self.write_bytes(topic_id, kind, name, text.encode("utf-8"))

    def read_text(self, topic_id: str, kind: ArtifactKind, name: str) -> str:
        return self.path_for(topic_id, kind, name).read_text(encoding="utf-8")

    def exists(self, topic_id: str, kind: ArtifactKind, name: str) -> bool:
        return self.path_for(topic_id, kind, name).is_file()

    def delete(self, topic_id: str, kind: ArtifactKind, name: str) -> None:
        self.path_for(topic_id, kind, name).unlink(missing_ok=True)
