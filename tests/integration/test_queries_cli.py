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
_COMPLETION = {
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": '{"queries": ["embodied navigation", "3d scene graphs"]}',
            }
        }
    ]
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
                        "keywords": ["spatial reasoning"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def run_plan(
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
            "queries",
            "plan",
            "--topic",
            TOPIC_ID,
            "--settings",
            str(settings_path),
            "--topics",
            str(topics_path),
            *extra,
        ],
    )


def saved_plans(tmp_path: Path) -> int:
    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        return int(connection.execute("SELECT COUNT(*) FROM query_plans").fetchone()[0])
    finally:
        connection.close()


def test_plan_prints_and_persists_the_resolved_queries(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = run_plan(
        monkeypatch,
        settings_path,
        topics_path,
        lambda request: httpx.Response(200, json=_COMPLETION),
    )

    assert result.exit_code == 0, result.output
    assert "Spatial Intelligence spatial reasoning" in result.output
    assert "embodied navigation" in result.output
    assert "query_expansion.v1" in result.output
    assert saved_plans(tmp_path) == 1


def test_no_save_leaves_nothing_behind(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = run_plan(
        monkeypatch,
        settings_path,
        topics_path,
        lambda request: httpx.Response(200, json=_COMPLETION),
        "--no-save",
    )

    assert result.exit_code == 0, result.output
    assert saved_plans(tmp_path) == 0


def test_an_inference_failure_still_returns_a_plan(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = run_plan(monkeypatch, settings_path, topics_path, lambda request: httpx.Response(503))

    assert result.exit_code == 0, result.output
    assert "fell back to the base query" in result.output
    assert "Spatial Intelligence spatial reasoning" in result.output
    assert saved_plans(tmp_path) == 1


def test_an_unknown_topic_exits_non_zero(settings_path: Path, topics_path: Path) -> None:
    # The lookup fails before any provider is contacted, so no transport is needed here.
    result = runner.invoke(
        app,
        [
            "queries",
            "plan",
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
