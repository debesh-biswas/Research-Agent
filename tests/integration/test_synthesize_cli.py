"""`research-agent synthesize` end to end: the full local pipeline over mocked endpoints.

Everything before synthesis is exercised for real against a mock transport; only the network and the
model are faked, so this is the closest thing to a full weekly run the suite has.
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
SYNTHESIS: dict[str, object] = {
    "major_developments": [
        {"text": "Metric control is now benchmarked", "supporting_paper_ids": ["doi_10_1234_abcd"]}
    ],
    "emerging_directions": [{"text": "Invented trend", "supporting_paper_ids": ["ghost"]}],
    "new_datasets": ["HM3D"],
    "changes_from_history": [],
}
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
        prompt = str(json.loads(request.content)["messages"]).lower()
        reply = (
            {
                "relevance": "high",
                "relevance_score": 0.9,
                "paper_type": "method",
                "action": "summarize",
                "confidence": 0.9,
                "reason_short": "Directly relevant.",
            }
            if "return relevance, relevance_score" in prompt
            else SYNTHESIS
            if "compare this week" in prompt
            else DRAFT
        )
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps(reply)}}]},
        )
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
def analyzed(monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path) -> None:
    """A topic taken all the way through analysis, ready to synthesize."""
    monkeypatch.setattr(cli, "DoclingParser", lambda: FakeParser())
    for command in ("classify", "acquire", "parse", "analyze"):
        invoke(monkeypatch, settings_path, topics_path, command, "--topic", TOPIC_ID)


def rows(tmp_path: Path, query: str) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        return [tuple(row) for row in connection.execute(query).fetchall()]
    finally:
        connection.close()


def test_synthesis_is_persisted_with_validated_references(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    topics_path: Path,
    tmp_path: Path,
    analyzed: None,
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "synthesize", "--topic", TOPIC_ID)

    assert result.exit_code == 0, result.output
    assert "1 analysis(es)" in result.output
    assert "0 previous period(s)" in result.output
    assert "1 unsupported finding(s) dropped" in result.output
    assert "development\tdoi_10_1234_abcd\tMetric control is now benchmarked" in result.output
    stored = rows(tmp_path, "SELECT payload_json FROM weekly_syntheses")
    assert len(stored) == 1
    payload = json.loads(str(stored[0][0]))
    assert payload["emerging_directions"] == []
    assert payload["paper_ids"] == ["doi_10_1234_abcd"]
    assert payload["prompt_version"] == "weekly_synthesis.v1"


def test_a_second_period_compares_against_history(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, analyzed: None
) -> None:
    invoke(monkeypatch, settings_path, topics_path, "synthesize", "--topic", TOPIC_ID)

    result = invoke(monkeypatch, settings_path, topics_path, "synthesize", "--topic", TOPIC_ID)

    assert "1 previous period(s)" in result.output


def test_a_provider_failure_exits_non_zero_and_records_an_error(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    topics_path: Path,
    tmp_path: Path,
    analyzed: None,
) -> None:
    result = invoke(
        monkeypatch,
        settings_path,
        topics_path,
        "synthesize",
        "--topic",
        TOPIC_ID,
        transport=broken_model,
    )

    assert result.exit_code == 1
    assert rows(tmp_path, "SELECT category, node FROM errors") == [
        ("MODEL_API_ERROR", "synthesize")
    ]


def test_synthesizing_without_analyses_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    invoke(monkeypatch, settings_path, topics_path, "classify", "--topic", TOPIC_ID)

    result = invoke(monkeypatch, settings_path, topics_path, "synthesize", "--topic", TOPIC_ID)

    assert result.exit_code == 1
    assert "no analyses" in result.output


def test_an_unknown_topic_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "synthesize", "--topic", "missing")

    assert result.exit_code == 1
    assert "Unknown topic" in result.output
