import sqlite3
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner, Result

from research_agent import cli
from research_agent.cli import app

runner = CliRunner()
TOPIC_ID = "spatial_intelligence"
PDF = b"%PDF-1.7\n" + b"x" * 200
_OPENALEX_PAGE = {
    "meta": {"next_cursor": None},
    "results": [
        {
            "id": "https://openalex.org/W1",
            "display_name": "Spatial Intelligence for Embodied Navigation",
            "doi": "https://doi.org/10.1234/abcd",
            "publication_date": "2026-09-18",
            "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
            "primary_location": {"pdf_url": "https://example.org/one.pdf"},
        },
        {
            "id": "https://openalex.org/W2",
            "display_name": "Mapping and Memory in Spatial Intelligence",
            "doi": "https://doi.org/10.1234/efgh",
            "publication_date": "2026-09-17",
            "authorships": [{"author": {"display_name": "Grace Hopper"}}],
            "primary_location": {"pdf_url": "https://example.org/two.pdf"},
        },
    ],
}


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump({"data_directory": str(tmp_path / "data")}), encoding="utf-8")
    return path


@pytest.fixture
def topics_path(tmp_path: Path) -> Path:
    path = tmp_path / "topics.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "topics": [
                    {
                        "id": TOPIC_ID,
                        "name": "Spatial Intelligence",
                        "keywords": ["embodied navigation"],
                        "discovery": {
                            "openalex": True,
                            "semantic_scholar": False,
                            "arxiv": False,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def invoke(
    monkeypatch: pytest.MonkeyPatch, handler: object, settings: Path, topics: Path, *arguments: str
) -> Result:
    monkeypatch.setattr(
        cli,
        "_http_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
    )
    return runner.invoke(app, [*arguments, "--settings", str(settings), "--topics", str(topics)])


def pdf_handler(request: httpx.Request) -> httpx.Response:
    if str(request.url).endswith(".pdf"):
        return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
    return httpx.Response(200, json=_OPENALEX_PAGE)


def classify(monkeypatch: pytest.MonkeyPatch, settings: Path, topics: Path) -> Result:
    return invoke(monkeypatch, pdf_handler, settings, topics, "classify", "--topic", TOPIC_ID)


def files(tmp_path: Path) -> list[tuple[str, str]]:
    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        return [
            (row[0], row[1])
            for row in connection.execute(
                "SELECT paper_id, kind FROM paper_files ORDER BY paper_id"
            ).fetchall()
        ]
    finally:
        connection.close()


def test_acquire_stores_the_selected_papers(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    classify(monkeypatch, settings_path, topics_path)

    result = invoke(
        monkeypatch, pdf_handler, settings_path, topics_path, "acquire", "--topic", TOPIC_ID
    )

    assert result.exit_code == 0, result.output
    assert "stored 2" in result.output
    stored = sorted((tmp_path / "data" / "topics" / TOPIC_ID / "papers").glob("*.pdf"))
    assert [path.name for path in stored] == ["doi_10_1234_abcd.pdf", "doi_10_1234_efgh.pdf"]
    assert files(tmp_path) == [("doi_10_1234_abcd", "pdf"), ("doi_10_1234_efgh", "pdf")]


def test_a_second_pass_costs_no_downloads(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    classify(monkeypatch, settings_path, topics_path)
    invoke(monkeypatch, pdf_handler, settings_path, topics_path, "acquire", "--topic", TOPIC_ID)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no download expected on a cached pass")

    result = invoke(monkeypatch, refuse, settings_path, topics_path, "acquire", "--topic", TOPIC_ID)

    assert result.exit_code == 0, result.output
    assert "cached 2" in result.output


def test_one_failing_download_leaves_the_other_stored(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    classify(monkeypatch, settings_path, topics_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("two.pdf"):
            return httpx.Response(404)
        return pdf_handler(request)

    result = invoke(
        monkeypatch, handler, settings_path, topics_path, "acquire", "--topic", TOPIC_ID
    )

    assert result.exit_code == 0, result.output
    assert "failed 1" in result.output
    assert "stored 1" in result.output
    assert files(tmp_path) == [("doi_10_1234_abcd", "pdf")]

    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        errors = connection.execute("SELECT category, node FROM errors").fetchall()
    finally:
        connection.close()
    assert errors == [("PDF_DOWNLOAD_ERROR", "acquire")]


def test_acquiring_without_a_run_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(
        monkeypatch, pdf_handler, settings_path, topics_path, "acquire", "--topic", TOPIC_ID
    )

    assert result.exit_code == 1
    assert "No run found" in result.output


def test_an_unknown_topic_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(
        monkeypatch, pdf_handler, settings_path, topics_path, "acquire", "--topic", "missing"
    )

    assert result.exit_code == 1
    assert "Unknown topic" in result.output
