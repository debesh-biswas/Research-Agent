"""`research-agent report` end to end: the whole pipeline through to the weekly deliverable.

Only the network and the model are faked; every stage in between runs for real, so this is the
closest the suite comes to a complete weekly run.
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
GAPS: dict[str, object] = {
    "gaps": [
        {
            "title": "No long-horizon benchmark",
            "description": "Existing benchmarks stop at 50 steps.",
            "supporting_paper_ids": ["doi_10_1234_abcd"],
            "confidence": 0.6,
        },
        {
            "title": "Invented gap",
            "description": "Cited to a paper that is not in this run.",
            "supporting_paper_ids": ["ghost"],
        },
    ]
}
IDEAS: dict[str, object] = {
    "ideas": [
        {
            "title": "Persistent map benchmark",
            "hypothesis": "Longer horizons expose memory failures.",
            "motivation": "Current scores saturate.",
            "supporting_paper_ids": ["doi_10_1234_abcd"],
            "identified_gap": "No long-horizon benchmark",
            "proposed_direction": "Extend ObjectNav episodes.",
            "evaluation_plan": "Compare SPL across horizons.",
            "risks": ["Compute cost"],
        }
    ]
}
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
        if "compare this week" in prompt:
            reply: dict[str, object] = SYNTHESIS
        elif "identify unaddressed research questions" in prompt:
            reply = GAPS
        elif "turn identified research gaps" in prompt:
            reply = IDEAS
        elif "executive summary" in prompt:
            reply = {"executive_summary": "One paper advanced embodied spatial control."}
        else:
            reply = DRAFT
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
def ideated(monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path) -> None:
    """A topic taken all the way through ideation, ready to report."""
    monkeypatch.setattr(cli, "DoclingParser", lambda: FakeParser())
    for command in ("classify", "acquire", "parse", "analyze", "synthesize", "ideate"):
        invoke(monkeypatch, settings_path, topics_path, command, "--topic", TOPIC_ID)


def rows(tmp_path: Path, query: str) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        return [tuple(row) for row in connection.execute(query).fetchall()]
    finally:
        connection.close()


def reports_dir(tmp_path: Path) -> Path:
    return tmp_path / "data" / "topics" / TOPIC_ID / "reports"


def test_the_weekly_report_is_written_with_every_section(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    topics_path: Path,
    tmp_path: Path,
    ideated: None,
) -> None:
    result = invoke(
        monkeypatch, settings_path, topics_path, "report", "generate", "--topic", TOPIC_ID
    )

    assert result.exit_code == 0, result.output
    assert "1 paper(s) report" in result.output
    assert "model-written summary" in result.output
    written = sorted(reports_dir(tmp_path).iterdir())
    assert len(written) == 1 and written[0].name.endswith("_weekly_report.md")
    text = written[0].read_text(encoding="utf-8")
    assert "One paper advanced embodied spatial control." in text
    assert "## Recommended Reading Order" in text
    assert "## Research Gaps" in text
    assert "Spatial Intelligence for Embodied Navigation" in text
    assert "<https://doi.org/10.1234/abcd>" in text


def test_latest_returns_the_stored_report(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    topics_path: Path,
    tmp_path: Path,
    ideated: None,
) -> None:
    invoke(monkeypatch, settings_path, topics_path, "report", "generate", "--topic", TOPIC_ID)

    result = invoke(monkeypatch, settings_path, topics_path, "report", "latest", TOPIC_ID)

    assert result.exit_code == 0, result.output
    assert result.output.strip().endswith("_weekly_report.md")


def test_latest_without_a_report_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "report", "latest", TOPIC_ID)

    assert result.exit_code == 1
    assert "No report stored" in result.output


def test_a_provider_failure_still_produces_a_report(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    topics_path: Path,
    tmp_path: Path,
    ideated: None,
) -> None:
    result = invoke(
        monkeypatch,
        settings_path,
        topics_path,
        "report",
        "generate",
        "--topic",
        TOPIC_ID,
        transport=broken_model,
    )

    assert result.exit_code == 0, result.output
    assert "assembled summary" in result.output
    assert sorted(reports_dir(tmp_path).iterdir())


def test_reporting_without_a_run_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(
        monkeypatch, settings_path, topics_path, "report", "generate", "--topic", TOPIC_ID
    )

    assert result.exit_code == 1
    assert "No run found" in result.output


def test_an_unknown_topic_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(
        monkeypatch, settings_path, topics_path, "report", "generate", "--topic", "missing"
    )

    assert result.exit_code == 1
    assert "Unknown topic" in result.output
