"""`research-agent parse` end to end, with the Docling backend replaced by a fake.

The real adapter is covered by `test_docling_parser.py` under `-m slow`; these tests are about the
command's plumbing, so they must not load torch.
"""

import sqlite3
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner, Result

from research_agent import cli
from research_agent.domain.documents import ParsedPaper, ParsedSection

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
        }
    ],
}


class FakeParser:
    name = "fake"

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    def parse(self, pdf_path: Path, paper_id: str) -> ParsedPaper:
        if self._error is not None:
            raise self._error
        return ParsedPaper(
            paper_id=paper_id,
            source_pdf_path=str(pdf_path),
            sections=[ParsedSection(title="Introduction", text="Body text.")],
            parser_name=self.name,
            parser_version="1.0",
        )


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


def handler(request: httpx.Request) -> httpx.Response:
    if str(request.url).endswith(".pdf"):
        return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
    return httpx.Response(200, json=_OPENALEX_PAGE)


def invoke(
    monkeypatch: pytest.MonkeyPatch, settings: Path, topics: Path, *arguments: str
) -> Result:
    monkeypatch.setattr(
        cli,
        "_http_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return runner.invoke(
        cli.app, [*arguments, "--settings", str(settings), "--topics", str(topics)]
    )


@pytest.fixture
def acquired(monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path) -> None:
    """A topic that has been classified and has one stored PDF, ready to parse."""
    invoke(monkeypatch, settings_path, topics_path, "classify", "--topic", TOPIC_ID)
    invoke(monkeypatch, settings_path, topics_path, "acquire", "--topic", TOPIC_ID)


def use_parser(monkeypatch: pytest.MonkeyPatch, parser: FakeParser) -> None:
    monkeypatch.setattr(cli, "DoclingParser", lambda: parser)


def test_parse_writes_artifacts_and_records_them(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    topics_path: Path,
    tmp_path: Path,
    acquired: None,
) -> None:
    use_parser(monkeypatch, FakeParser())

    result = invoke(monkeypatch, settings_path, topics_path, "parse", "--topic", TOPIC_ID)

    assert result.exit_code == 0, result.output
    assert "parsed 1" in result.output
    parsed_dir = tmp_path / "data" / "topics" / TOPIC_ID / "parsed"
    assert sorted(path.name for path in parsed_dir.iterdir()) == [
        "doi_10_1234_abcd.json",
        "doi_10_1234_abcd.md",
    ]

    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        kinds = [
            row[0]
            for row in connection.execute("SELECT kind FROM paper_files ORDER BY kind").fetchall()
        ]
    finally:
        connection.close()
    assert kinds == ["parsed", "pdf"]


def test_a_second_pass_is_cached(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, acquired: None
) -> None:
    use_parser(monkeypatch, FakeParser())
    invoke(monkeypatch, settings_path, topics_path, "parse", "--topic", TOPIC_ID)

    result = invoke(monkeypatch, settings_path, topics_path, "parse", "--topic", TOPIC_ID)

    assert "cached 1" in result.output


def test_a_parse_failure_is_recorded_as_a_run_error(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    topics_path: Path,
    tmp_path: Path,
    acquired: None,
) -> None:
    use_parser(monkeypatch, FakeParser(error=RuntimeError("unreadable")))

    result = invoke(monkeypatch, settings_path, topics_path, "parse", "--topic", TOPIC_ID)

    assert result.exit_code == 0, result.output
    assert "failed 1" in result.output

    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        errors = connection.execute("SELECT category, node FROM errors").fetchall()
    finally:
        connection.close()
    assert errors == [("PDF_PARSE_ERROR", "parse")]


def test_parsing_without_acquired_pdfs_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    invoke(monkeypatch, settings_path, topics_path, "classify", "--topic", TOPIC_ID)

    result = invoke(monkeypatch, settings_path, topics_path, "parse", "--topic", TOPIC_ID)

    assert result.exit_code == 1
    assert "no stored PDFs" in result.output


def test_an_unknown_topic_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "parse", "--topic", "missing")

    assert result.exit_code == 1
    assert "Unknown topic" in result.output
