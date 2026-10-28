"""`research-agent run`, `run-all` and `schedule generate` over mocked endpoints.

The parser backend is faked through the wiring's injection point, so these never load torch.
"""

import json
import sqlite3
from pathlib import Path

import httpx
import pytest
import yaml
from typer.testing import CliRunner, Result

from research_agent import cli
from research_agent.operations import wiring
from research_agent.operations.locks import lock_path
from tests.integration.test_workflow_graph import FakeParser, handler

runner = CliRunner()
TOPIC_ID = "spatial_intelligence"
OTHER_ID = "disabled_topic"


@pytest.fixture
def settings_path(tmp_path: Path) -> Path:
    path = tmp_path / "settings.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "data_directory": str(tmp_path / "data"),
                "retries": {"academic_apis": 0, "nim": 0, "pdf_download": 0},
            }
        ),
        encoding="utf-8",
    )
    return path


def topic_entry(topic_id: str, enabled: bool = True) -> dict[str, object]:
    return {
        "id": topic_id,
        "name": topic_id.replace("_", " ").title(),
        "enabled": enabled,
        "keywords": ["embodied navigation"],
        "discovery": {"openalex": True, "semantic_scholar": False, "arxiv": False},
    }


@pytest.fixture
def topics_path(tmp_path: Path) -> Path:
    path = tmp_path / "topics.yaml"
    path.write_text(
        yaml.safe_dump({"topics": [topic_entry(TOPIC_ID), topic_entry(OTHER_ID, enabled=False)]}),
        encoding="utf-8",
    )
    return path


def invoke(
    monkeypatch: pytest.MonkeyPatch,
    settings: Path,
    topics: Path,
    *arguments: str,
    transport: object = None,
    parser: FakeParser | None = None,
) -> Result:
    respond = transport or handler()
    monkeypatch.setattr(
        cli,
        "_http_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(respond)),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(wiring, "DoclingParser", lambda: parser or FakeParser())
    return runner.invoke(
        cli.app, [*arguments, "--settings", str(settings), "--topics", str(topics)]
    )


def rows(tmp_path: Path, query: str) -> list[tuple[object, ...]]:
    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        return [tuple(row) for row in connection.execute(query).fetchall()]
    finally:
        connection.close()


def test_a_single_run_completes_and_reports(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "run", TOPIC_ID)

    assert result.exit_code == 0, result.output
    assert "completed\tspatial_intelligence" in result.output
    assert "_weekly_report.md" in result.output
    statuses = rows(tmp_path, "SELECT status FROM runs")
    assert statuses == [("completed",)]
    ((usage,),) = rows(tmp_path, "SELECT json_extract(summary_json, '$.model_usage') FROM runs")
    (local,) = json.loads(str(usage))
    assert local["provider"] == "local" and local["calls"] > 0
    ((queries,),) = rows(tmp_path, "SELECT json_extract(summary_json, '$.queries') FROM runs")
    assert json.loads(str(queries)), "the run records what it searched for"
    reports = tmp_path / "data" / "topics" / TOPIC_ID / "reports"
    assert list(reports.iterdir())


def test_the_lock_is_released_after_a_run(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    invoke(monkeypatch, settings_path, topics_path, "run", TOPIC_ID)

    assert not lock_path(tmp_path / "data", TOPIC_ID).exists()


def test_an_overlapping_run_is_refused(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    held = lock_path(tmp_path / "data", TOPIC_ID)
    held.parent.mkdir(parents=True, exist_ok=True)
    held.write_text("not a pid", encoding="utf-8")

    result = invoke(monkeypatch, settings_path, topics_path, "run", TOPIC_ID)

    assert result.exit_code == 1
    assert "locked\tspatial_intelligence" in result.output
    assert rows(tmp_path, "SELECT status FROM runs") == []


def test_a_partial_failure_still_succeeds_but_is_marked_degraded(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = invoke(
        monkeypatch, settings_path, topics_path, "run", TOPIC_ID, transport=handler(pdf=False)
    )

    assert result.exit_code == 0, result.output
    assert "degraded\tspatial_intelligence" in result.output
    assert rows(tmp_path, "SELECT status FROM runs") == [("degraded",)]


def test_a_disabled_topic_is_skipped_and_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "run", OTHER_ID)

    assert result.exit_code == 1
    assert "skipped\tdisabled_topic" in result.output
    assert "disabled" in result.output


def test_an_unknown_topic_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "run", "missing")

    assert result.exit_code == 1
    assert "Unknown topic" in result.output


def test_run_all_runs_the_enabled_topics_and_skips_the_rest(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = invoke(monkeypatch, settings_path, topics_path, "run-all")

    assert result.exit_code == 0, result.output
    assert "completed\tspatial_intelligence" in result.output
    assert "skipped\tdisabled_topic" in result.output
    assert "2 topic(s): completed 1, skipped 1" in result.output
    assert rows(tmp_path, "SELECT topic_id FROM runs") == [(TOPIC_ID,)]


def test_a_generated_launchd_schedule_is_deterministic_and_secret_free(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    first = invoke(
        monkeypatch, settings_path, topics_path, "schedule", "generate", "--topic", TOPIC_ID
    )
    second = invoke(
        monkeypatch, settings_path, topics_path, "schedule", "generate", "--topic", TOPIC_ID
    )

    assert first.exit_code == 0, first.output
    assert first.output == second.output
    assert "<string>run</string>" in first.output
    assert "launchctl bootstrap" in first.output
    assert "API_KEY" not in first.output


def test_a_cron_schedule_can_be_written_to_a_file(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "out" / "weekly.crontab"

    result = invoke(
        monkeypatch,
        settings_path,
        topics_path,
        "schedule",
        "generate",
        "--topic",
        TOPIC_ID,
        "--backend",
        "cron",
        "--at",
        "06:15",
        "--output",
        str(destination),
    )

    assert result.exit_code == 0, result.output
    line = destination.read_text(encoding="utf-8")
    assert line.startswith("15 6 * * 0 cd ")
    assert f"research-agent run {TOPIC_ID}" in line
    assert "crontab" in result.output


def test_an_invalid_schedule_time_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(
        monkeypatch,
        settings_path,
        topics_path,
        "schedule",
        "generate",
        "--topic",
        TOPIC_ID,
        "--at",
        "half past seven",
    )

    assert result.exit_code == 1
    assert "Unable to schedule" in result.output


def test_an_unsupported_backend_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    result = invoke(
        monkeypatch,
        settings_path,
        topics_path,
        "schedule",
        "generate",
        "--topic",
        TOPIC_ID,
        "--backend",
        "systemd",
    )

    assert result.exit_code == 1
    assert "unsupported scheduler backend" in result.output


def test_a_second_run_reuses_screening_for_unchanged_papers(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    respond = handler()
    screenings: list[str] = []

    def counting(request: httpx.Request) -> httpx.Response:
        if b"research-paper screener" in request.content:
            screenings.append(str(request.url))
        return respond(request)

    first = invoke(monkeypatch, settings_path, topics_path, "run", TOPIC_ID, transport=counting)
    asked_first = len(screenings)
    second = invoke(monkeypatch, settings_path, topics_path, "run", TOPIC_ID, transport=counting)

    assert first.exit_code == 0 and second.exit_code == 0, second.output
    assert asked_first > 0
    assert len(screenings) == asked_first, "the second run asked the model nothing new"
    per_run = rows(
        tmp_path,
        "SELECT c.run_id, COUNT(*), SUM(json_extract(c.raw_response_json, '$.reused') IS 1) "
        "FROM classifications c JOIN runs r ON r.id = c.run_id "
        "GROUP BY c.run_id ORDER BY MIN(r.started_at)",
    )
    assert [(count, reused) for _, count, reused in per_run] == [
        (asked_first, 0),
        (asked_first, asked_first),
    ]


def test_a_paper_read_from_its_abstract_after_a_failed_download_is_retried_next_run(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    down = invoke(
        monkeypatch, settings_path, topics_path, "run", TOPIC_ID, transport=handler(pdf=False)
    )
    assert down.exit_code == 0, down.output
    reads = (
        "SELECT a.paper_id, json_extract(a.payload_json, '$.abstract_only') FROM paper_analyses a "
        "JOIN runs r ON r.id = a.run_id ORDER BY r.started_at, a.paper_id"
    )
    first = rows(tmp_path, reads)
    assert first and all(flag == 1 for _, flag in first)

    back = invoke(monkeypatch, settings_path, topics_path, "run", TOPIC_ID)

    assert back.exit_code == 0, back.output
    upgraded = rows(tmp_path, reads)[len(first) :]
    assert [(paper, flag) for paper, flag in upgraded] == [(paper, 0) for paper, _ in first]
    kept = rows(
        tmp_path,
        "SELECT paper_id, COUNT(DISTINCT run_id) FROM selections WHERE selected = 1 "
        "GROUP BY paper_id ORDER BY paper_id",
    )
    assert kept == [(paper, 2) for paper, _ in first], "both runs kept them"


def test_a_paper_already_read_in_full_is_not_redone(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    assert invoke(monkeypatch, settings_path, topics_path, "run", TOPIC_ID).exit_code == 0
    once = rows(tmp_path, "SELECT COUNT(*) FROM paper_analyses")
    assert invoke(monkeypatch, settings_path, topics_path, "run", TOPIC_ID).exit_code == 0

    assert rows(tmp_path, "SELECT COUNT(*) FROM paper_analyses") == once
    reasons = rows(tmp_path, "SELECT DISTINCT reason FROM selections WHERE selected = 0")
    assert reasons == [("already_analyzed",)]
