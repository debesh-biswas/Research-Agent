"""Backups round-trip the library; restores never delete and never trust the archive."""

import json
import zipfile
from pathlib import Path

import pytest

from research_agent.config import TopicSettings
from research_agent.operations.backup import BackupError, create_backup, restore_backup
from research_agent.operations.locks import lock_path
from research_agent.storage.database import apply_migrations, connect
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.topics import SqliteTopicRepository
from tests.unit.conftest import candidate


def _library(root: Path, topic: str = "spatial") -> Path:
    connection = connect(root / "research_agent.db")
    apply_migrations(connection)
    SqliteTopicRepository(connection).add(TopicSettings(id=topic, name=topic.title()))
    connection.close()
    pdf = root / "topics" / topic / "pdfs" / "paper.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 " + topic.encode())
    report = root / "topics" / topic / "reports" / "2026-10-27_weekly_report.md"
    report.parent.mkdir(parents=True)
    report.write_text("# Weekly\n", encoding="utf-8")
    (root / "locks").mkdir()
    return root


def _topics(root: Path) -> list[str]:
    connection = connect(root / "research_agent.db")
    try:
        return [topic.id for topic in SqliteTopicRepository(connection).list()]
    finally:
        connection.close()


def test_a_backup_restores_into_an_empty_folder_byte_for_byte(tmp_path: Path) -> None:
    library = _library(tmp_path / "data")
    archive = create_backup(library, tmp_path / "backup.zip")

    restored = tmp_path / "restored"
    assert restore_backup(archive, restored) is None

    assert _topics(restored) == ["spatial"]
    for relative in (
        "topics/spatial/pdfs/paper.pdf",
        "topics/spatial/reports/2026-10-27_weekly_report.md",
    ):
        assert (restored / relative).read_bytes() == (library / relative).read_bytes()
    assert not (restored / "backup.json").exists() and not (restored / "locks").exists()


def test_restoring_over_a_library_moves_it_aside(tmp_path: Path) -> None:
    archive = create_backup(_library(tmp_path / "old", "from_backup"), tmp_path / "backup.zip")
    current = _library(tmp_path / "data", "current")

    moved = restore_backup(archive, current)

    assert _topics(current) == ["from_backup"]
    assert moved is not None and _topics(moved) == ["current"], "the old library is kept"


@pytest.mark.parametrize(
    "members",
    [
        {"backup.json": "{}", "research_agent.db": ""},
        {"research_agent.db": ""},
        {
            "backup.json": '{"kind": "research-agent-backup"}',
            "research_agent.db": "",
            "../evil": "",
        },
        {"backup.json": '{"kind": "research-agent-backup"}', "research_agent.db": "", "/etc/x": ""},
        {"backup.json": '{"kind": "research-agent-backup"}', "research_agent.db": "", "a/b": ""},
    ],
    ids=["wrong-kind", "no-manifest", "parent-escape", "absolute", "outside-topics"],
)
def test_an_untrustworthy_archive_is_refused_before_anything_is_written(
    tmp_path: Path, members: dict[str, str]
) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bad:
        for name, body in members.items():
            bad.writestr(name, body)
    target = tmp_path / "data"

    with pytest.raises(BackupError):
        restore_backup(archive, target)
    assert not target.exists()


def test_a_file_that_is_not_a_zip_is_refused(tmp_path: Path) -> None:
    archive = tmp_path / "notes.txt"
    archive.write_text("hello", encoding="utf-8")

    with pytest.raises(BackupError, match="not a backup"):
        restore_backup(archive, tmp_path / "data")


def test_backup_and_restore_wait_for_a_running_run(tmp_path: Path) -> None:
    library = _library(tmp_path / "data")
    archive = create_backup(library, tmp_path / "backup.zip")
    lock_path(library, "spatial").write_text("not a pid", encoding="utf-8")  # counts as held

    with pytest.raises(BackupError, match="run is in progress"):
        create_backup(library, tmp_path / "second.zip")
    with pytest.raises(BackupError, match="run is in progress"):
        restore_backup(archive, library)
    assert _topics(library) == ["spatial"]


def test_there_is_nothing_to_back_up_without_a_library(tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="no library"):
        create_backup(tmp_path / "empty", tmp_path / "backup.zip")


def test_the_manifest_names_the_app_version(tmp_path: Path) -> None:
    archive = create_backup(_library(tmp_path / "data"), tmp_path / "backup.zip")
    with zipfile.ZipFile(archive) as opened:
        manifest = json.loads(opened.read("backup.json"))
    assert manifest["kind"] == "research-agent-backup" and manifest["app_version"]


def test_a_restore_elsewhere_repoints_recorded_file_paths(tmp_path: Path) -> None:
    library = _library(tmp_path / "data")
    connection = connect(library / "research_agent.db")
    papers = SqlitePaperRepository(connection)
    paper_id = papers.upsert(candidate(title="Maps", doi="10.1/m"))
    pdf = (library / "topics" / "spatial" / "pdfs" / "paper.pdf").resolve()
    papers.record_file(paper_id, "pdf", str(pdf), 10, "0" * 64)
    papers.record_file(paper_id, "parsed", "/somewhere/else/paper.md", 10, "0" * 64)
    connection.close()
    archive = create_backup(library, tmp_path / "backup.zip")

    elsewhere = tmp_path / "new-machine" / "library"
    restore_backup(archive, elsewhere)

    connection = connect(elsewhere / "research_agent.db")
    files = SqlitePaperRepository(connection).files_for(paper_id)
    connection.close()
    assert files["pdf"] == str(elsewhere.resolve() / "topics" / "spatial" / "pdfs" / "paper.pdf")
    assert Path(files["pdf"]).is_file()
    assert files["parsed"] == "/somewhere/else/paper.md", "paths outside the library are left alone"
