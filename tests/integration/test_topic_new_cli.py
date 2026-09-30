import sqlite3
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from research_agent import cli
from research_agent.cli import app
from research_agent.operations.runner import RunOutcome

runner = CliRunner()
_COMPLETION = {
    "choices": [{"message": {"role": "assistant", "content": '{"keywords": ["robot grasping"]}'}}]
}


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(yaml.safe_dump({"data_directory": str(tmp_path / "data")}), encoding="utf-8")
    return path


@pytest.fixture
def topics_path(tmp_path: Path) -> Path:
    path = tmp_path / "topics.yaml"
    path.write_text(yaml.safe_dump({"topics": []}), encoding="utf-8")
    return path


def _mock_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_COMPLETION)

    monkeypatch.setattr(
        cli,
        "_http_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_declining_leaves_no_topic_stored(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    _mock_client(monkeypatch)

    result = runner.invoke(
        app,
        [
            "topic",
            "new",
            "--id",
            "robotics",
            "--name",
            "Robotics",
            "--settings",
            str(settings_path),
            "--topics",
            str(topics_path),
        ],
        input="n\n",
    )

    assert result.exit_code == 1
    assert "Suggested keywords: robot grasping" in result.stdout

    listed = runner.invoke(
        app,
        ["topic", "list", "--settings", str(settings_path), "--topics", str(topics_path)],
    )
    assert "robotics" not in listed.stdout


def test_confirming_creates_the_topic_and_starts_the_pipeline(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    _mock_client(monkeypatch)
    calls: list[str] = []

    def fake_run_one(
        connection: sqlite3.Connection, application: object, topic: object
    ) -> RunOutcome:
        calls.append(topic.id)  # type: ignore[attr-defined]
        return RunOutcome(topic_id=topic.id, conclusion="completed")  # type: ignore[attr-defined]

    monkeypatch.setattr(cli, "_run_one", fake_run_one)

    result = runner.invoke(
        app,
        [
            "topic",
            "new",
            "--id",
            "robotics",
            "--name",
            "Robotics",
            "--settings",
            str(settings_path),
            "--topics",
            str(topics_path),
        ],
        input="y\n",
    )

    assert result.exit_code == 0, result.stdout
    assert calls == ["robotics"]

    listed = runner.invoke(
        app,
        ["topic", "list", "--settings", str(settings_path), "--topics", str(topics_path)],
    )
    assert "robotics" in listed.stdout
