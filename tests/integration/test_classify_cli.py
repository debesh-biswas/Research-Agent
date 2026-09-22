import asyncio
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

_OPENALEX_PAGE = {
    "meta": {"next_cursor": None},
    "results": [
        {
            "id": "https://openalex.org/W1",
            "display_name": "Spatial Intelligence for Embodied Navigation",
            "doi": "https://doi.org/10.1234/abcd",
            "publication_date": "2026-09-18",
            "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
            "primary_location": {"landing_page_url": "https://example.org/w1"},
        },
        {
            "id": "https://openalex.org/W2",
            "display_name": "Tax Policy in Northern Europe",
            "doi": "https://doi.org/10.1234/efgh",
            "publication_date": "2026-09-17",
            "authorships": [{"author": {"display_name": "Grace Hopper"}}],
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


def run_classify(
    monkeypatch: pytest.MonkeyPatch,
    settings_path: Path,
    topics_path: Path,
    handler: object,
    *extra: str,
) -> Result:
    monkeypatch.setattr(
        cli,
        "_http_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
    )
    return runner.invoke(
        app,
        [
            "classify",
            "--topic",
            TOPIC_ID,
            "--settings",
            str(settings_path),
            "--topics",
            str(topics_path),
            *extra,
        ],
    )


def counts(tmp_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("runs", "papers", "classifications")
        }
    finally:
        connection.close()


def test_classify_prints_verdicts_and_persists_a_run(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = run_classify(
        monkeypatch,
        settings_path,
        topics_path,
        lambda request: httpx.Response(200, json=_OPENALEX_PAGE),
    )

    assert result.exit_code == 0, result.output
    assert "2 verdict(s) for spatial_intelligence via classifier A" in result.output
    assert "deep_read" in result.output
    assert "ignore" in result.output
    assert "saved as run " in result.output
    assert counts(tmp_path) == {"runs": 1, "papers": 2, "classifications": 2}


def test_no_save_leaves_nothing_behind(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = run_classify(
        monkeypatch,
        settings_path,
        topics_path,
        lambda request: httpx.Response(200, json=_OPENALEX_PAGE),
        "--no-save",
    )

    assert result.exit_code == 0, result.output
    assert counts(tmp_path) == {"runs": 0, "papers": 0, "classifications": 0}


def test_an_explicit_query_is_sent_to_the_sources(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.params.get("search", ""))
        return httpx.Response(200, json=_OPENALEX_PAGE)

    result = run_classify(
        monkeypatch, settings_path, topics_path, handler, "--query", "scene graphs"
    )

    assert result.exit_code == 0, result.output
    assert seen == ["scene graphs"]


def test_a_source_failure_still_completes_the_command(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    result = run_classify(
        monkeypatch, settings_path, topics_path, lambda request: httpx.Response(500)
    )

    assert result.exit_code == 0, result.output
    assert "0 verdict(s)" in result.output
    assert counts(tmp_path) == {"runs": 1, "papers": 0, "classifications": 0}


def test_an_unknown_topic_exits_non_zero(settings_path: Path, topics_path: Path) -> None:
    # The lookup fails before any source is contacted, so no transport is needed here.
    result = runner.invoke(
        app,
        [
            "classify",
            "--topic",
            "not_a_topic",
            "--settings",
            str(settings_path),
            "--topics",
            str(topics_path),
        ],
    )

    assert result.exit_code == 1
    assert "Unknown topic" in result.output


async def _no_sleep(delay: float) -> None:
    return None
