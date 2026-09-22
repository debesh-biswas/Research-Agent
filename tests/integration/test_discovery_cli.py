import asyncio
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner, Result

from research_agent import cli
from research_agent.cli import app

runner = CliRunner()

_OPENALEX_PAGE = {
    "meta": {"next_cursor": None},
    "results": [
        {
            "id": "https://openalex.org/W1",
            "display_name": "Embodied Spatial Intelligence for Robots",
            "doi": "https://doi.org/10.1234/abcd",
            "publication_date": "2026-09-18",
            "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
            "primary_location": {"landing_page_url": "https://example.org/w1"},
        }
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
                        "id": "spatial_intelligence",
                        "name": "Spatial Intelligence",
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


@pytest.fixture
def mocked_openalex(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_OPENALEX_PAGE)

    def factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(cli, "_http_client", factory)
    return requests


def _invoke(settings: Path, topics: Path, *arguments: str) -> Result:
    return runner.invoke(
        app,
        ["discover", *arguments, "--settings", str(settings), "--topics", str(topics)],
    )


def test_discover_prints_counts_and_candidates(
    settings_path: Path, topics_path: Path, mocked_openalex: list[httpx.Request]
) -> None:
    result = _invoke(
        settings_path,
        topics_path,
        "--topic",
        "spatial_intelligence",
        "--query",
        "embodied spatial reasoning",
    )

    assert result.exit_code == 0
    assert "1 candidate(s)" in result.stdout
    assert "openalex 1" in result.stdout
    assert "doi_10_1234_abcd" in result.stdout
    assert "Embodied Spatial Intelligence for Robots" in result.stdout
    assert len(mocked_openalex) == 1


def test_discover_reports_a_source_failure_without_failing_the_command(
    settings_path: Path, topics_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    monkeypatch.setattr(
        cli,
        "_http_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    result = _invoke(
        settings_path, topics_path, "--topic", "spatial_intelligence", "--query", "anything"
    )

    assert result.exit_code == 0
    assert "0 candidate(s)" in result.stdout


def test_discover_rejects_an_unknown_topic(settings_path: Path, topics_path: Path) -> None:
    result = _invoke(settings_path, topics_path, "--topic", "missing", "--query", "anything")

    assert result.exit_code == 1


async def _no_sleep(delay: float) -> None:
    return None
