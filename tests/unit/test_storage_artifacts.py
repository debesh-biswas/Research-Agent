from pathlib import Path

import pytest

from research_agent.storage.artifacts import (
    ArtifactPathError,
    LocalArtifactStore,
    safe_name,
)

TOPIC = "spatial_intelligence"


def _store(tmp_path: Path) -> LocalArtifactStore:
    return LocalArtifactStore(tmp_path)


def test_layout_matches_the_specified_tree(tmp_path: Path) -> None:
    path = _store(tmp_path).path_for(TOPIC, "papers", "doi_10_1234_abcd.pdf")

    assert path == tmp_path / "topics" / TOPIC / "papers" / "doi_10_1234_abcd.pdf"


def test_filenames_are_deterministic_and_safe(tmp_path: Path) -> None:
    store = _store(tmp_path)

    first = store.path_for(TOPIC, "analyses", "DOI 10.1234/abcd.json")
    second = store.path_for(TOPIC, "analyses", "DOI 10.1234/abcd.json")

    assert first == second
    assert first.name == "doi_10.1234_abcd.json"


@pytest.mark.parametrize("name", ["../../escape.pdf", "/etc/passwd", "a/../../b.pdf"])
def test_traversal_attempts_stay_inside_the_topic_directory(tmp_path: Path, name: str) -> None:
    root = (tmp_path / "topics" / TOPIC / "papers").resolve()

    assert _store(tmp_path).path_for(TOPIC, "papers", name).is_relative_to(root)


@pytest.mark.parametrize("name", ["..", "", "///", "..."])
def test_unusable_names_are_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(ArtifactPathError):
        _store(tmp_path).path_for(TOPIC, "papers", name)


def test_a_topic_id_with_a_separator_cannot_escape(tmp_path: Path) -> None:
    path = _store(tmp_path).path_for("../secrets", "reports", "weekly.md")

    assert path.is_relative_to((tmp_path / "topics").resolve())


def test_write_then_read_round_trips_and_leaves_no_temp_file(tmp_path: Path) -> None:
    store = _store(tmp_path)

    path = store.write_text(TOPIC, "reports", "2026-09-22_weekly_report.md", "# Weekly\n")

    assert store.read_text(TOPIC, "reports", "2026-09-22_weekly_report.md") == "# Weekly\n"
    assert store.exists(TOPIC, "reports", "2026-09-22_weekly_report.md")
    assert [child.name for child in path.parent.iterdir()] == [path.name]


def test_overwrite_replaces_cleanly(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_bytes(TOPIC, "papers", "paper.pdf", b"first")

    store.write_bytes(TOPIC, "papers", "paper.pdf", b"second")

    assert store.path_for(TOPIC, "papers", "paper.pdf").read_bytes() == b"second"


def test_delete_is_forgiving(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.write_text(TOPIC, "parsed", "paper.md", "text")

    store.delete(TOPIC, "parsed", "paper.md")
    store.delete(TOPIC, "parsed", "paper.md")

    assert not store.exists(TOPIC, "parsed", "paper.md")


def test_safe_name_collapses_unsupported_characters() -> None:
    # A non-breaking space is one of the characters provider metadata actually contains.
    assert safe_name("Embodied  Spatial/AI\u00a0v2") == "embodied_spatial_ai_v2"
