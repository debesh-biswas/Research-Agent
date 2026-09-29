"""`research-agent analyze` end to end: classify, acquire, parse, then analyze over a mocked model.

The parser backend is faked so the suite never loads torch; the model endpoint is a mock transport,
so nothing here reaches a network or a key.
"""

import json
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
DRAFT: dict[str, object] = {
    "research_problem": "Agents cannot reason about unseen rooms.",
    "main_contribution": "A persistent spatial memory module.",
    "method": "A transformer over a metric map.",
    "datasets": ["HM3D"],
    "benchmarks": ["ObjectNav"],
    "main_results": ["+7 SPL over the baseline"],
    "key_claims": [{"text": "Memory improves navigation", "source_section": "Results", "page": 2}],
    "topic_relevance": "Directly on topic.",
}
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

    def parse(self, pdf_path: Path, paper_id: str) -> ParsedPaper:
        return ParsedPaper(
            paper_id=paper_id,
            source_pdf_path=str(pdf_path),
            title="A Parsed Paper",
            sections=[
                ParsedSection(title="Introduction", text="Background."),
                ParsedSection(title="Results", text="SPL rises from 0.51 to 0.58.", page=2),
            ],
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
    url = str(request.url)
    if url.endswith(".pdf"):
        return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
    if url.endswith("/chat/completions"):
        body = json.loads(request.content)
        if "return relevance, relevance_score" in str(body["messages"]).lower():
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    '{"relevance":"high","relevance_score":0.9,'
                                    '"paper_type":"method","action":"summarize",'
                                    '"confidence":0.9,"reason_short":"Directly relevant."}'
                                ),
                            }
                        }
                    ]
                },
            )
        if "analyse one academic paper" in str(body["messages"]).lower():
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"role": "assistant", "content": json.dumps(DRAFT)}}]
                },
            )
        return httpx.Response(500, json={"error": "unexpected prompt"})
    return httpx.Response(200, json=_OPENALEX_PAGE)


def broken_model(request: httpx.Request) -> httpx.Response:
    if str(request.url).endswith("/chat/completions"):
        return httpx.Response(503, json={"error": "upstream is unwell"})
    return handler(request)


def invoke(
    monkeypatch: pytest.MonkeyPatch,
    settings: Path,
    topics: Path,
    *arguments: str,
    transport: object = None,
) -> Result:
    monkeypatch.setattr(
        cli,
        "_http_client",
        lambda timeout: httpx.AsyncClient(
            transport=httpx.MockTransport(transport or handler)  # type: ignore[arg-type]
        ),
    )
    return runner.invoke(
        cli.app, [*arguments, "--settings", str(settings), "--topics", str(topics)]
    )


@pytest.fixture
def parsed(monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path) -> None:
    """A topic taken all the way to stored parsed text, ready to analyze."""
    monkeypatch.setattr(cli, "DoclingParser", lambda: FakeParser())
    invoke(monkeypatch, settings_path, topics_path, "classify", "--topic", TOPIC_ID)
    invoke(monkeypatch, settings_path, topics_path, "acquire", "--topic", TOPIC_ID)
    invoke(monkeypatch, settings_path, topics_path, "parse", "--topic", TOPIC_ID)


def rows(tmp_path: Path, query: str) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        return [tuple(row) for row in connection.execute(query).fetchall()]
    finally:
        connection.close()


def test_analyze_persists_an_analysis_and_writes_a_card(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    topics_path: Path,
    tmp_path: Path,
    parsed: None,
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "analyze", "--topic", TOPIC_ID)

    assert result.exit_code == 0, result.output
    assert "analyzed 1" in result.output
    assert "full text" in result.output
    card = tmp_path / "data" / "topics" / TOPIC_ID / "analyses" / "doi_10_1234_abcd.md"
    assert "## Main contribution" in card.read_text(encoding="utf-8")
    assert rows(tmp_path, "SELECT paper_id FROM paper_analyses") == [("doi_10_1234_abcd",)]
    analyzed = rows(tmp_path, "SELECT last_analyzed_at, analyzed_hash FROM papers")
    assert analyzed[0][0] is not None and analyzed[0][1] is not None


def test_a_second_pass_is_cached(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, parsed: None
) -> None:
    invoke(monkeypatch, settings_path, topics_path, "analyze", "--topic", TOPIC_ID)

    result = invoke(monkeypatch, settings_path, topics_path, "analyze", "--topic", TOPIC_ID)

    assert "cached 1" in result.output


def test_a_provider_failure_is_recorded_per_paper(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    topics_path: Path,
    tmp_path: Path,
    parsed: None,
) -> None:
    result = invoke(
        monkeypatch,
        settings_path,
        topics_path,
        "analyze",
        "--topic",
        TOPIC_ID,
        transport=broken_model,
    )

    assert result.exit_code == 0, result.output
    assert "failed 1" in result.output
    assert rows(tmp_path, "SELECT category, node FROM errors") == [("MODEL_API_ERROR", "analyze")]
    assert rows(tmp_path, "SELECT paper_id FROM paper_analyses") == []


def test_analyzing_without_a_run_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "analyze", "--topic", TOPIC_ID)

    assert result.exit_code == 1
    assert "No run found" in result.output


def test_an_unknown_topic_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "analyze", "--topic", "missing")

    assert result.exit_code == 1
    assert "Unknown topic" in result.output
