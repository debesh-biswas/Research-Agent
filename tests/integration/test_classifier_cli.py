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
_VERDICT = (
    '{"relevance": "medium", "relevance_score": 0.5, "paper_type": "method", '
    '"action": "summarize", "confidence": 0.7, "reason_short": "related work"}'
)
_OPENALEX_PAGE = {
    "meta": {"next_cursor": None},
    "results": [
        {
            "id": "https://openalex.org/W1",
            "display_name": "Spatial Intelligence for Embodied Navigation",
            "doi": "https://doi.org/10.1234/abcd",
            "publication_date": "2026-09-18",
            "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
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
                        "id": TOPIC_ID,
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


def invoke(settings: Path, topics: Path, *arguments: str) -> Result:
    return runner.invoke(app, [*arguments, "--settings", str(settings), "--topics", str(topics)])


def stored_classifier(tmp_path: Path) -> tuple[str, str | None]:
    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        row = connection.execute(
            "SELECT active_classifier, shadow_classifier FROM topics WHERE id = ?", (TOPIC_ID,)
        ).fetchone()
    finally:
        connection.close()
    return row[0], row[1]


def test_setting_the_classifier_persists_for_later_commands(
    settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = invoke(settings_path, topics_path, "classifier", "set", "B", "--topic", TOPIC_ID)

    assert result.exit_code == 0, result.output
    assert stored_classifier(tmp_path) == ("B", None)


def test_a_shadow_classifier_can_be_set_and_cleared(
    settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    invoke(
        settings_path, topics_path, "classifier", "set", "A", "--topic", TOPIC_ID, "--shadow", "B"
    )
    assert stored_classifier(tmp_path) == ("A", "B")

    invoke(
        settings_path,
        topics_path,
        "classifier",
        "set",
        "A",
        "--topic",
        TOPIC_ID,
        "--shadow",
        "none",
    )
    assert stored_classifier(tmp_path) == ("A", None)


def test_a_shadow_equal_to_the_active_classifier_exits_non_zero(
    settings_path: Path, topics_path: Path
) -> None:
    result = invoke(
        settings_path, topics_path, "classifier", "set", "B", "--topic", TOPIC_ID, "--shadow", "B"
    )

    assert result.exit_code == 1


def test_setting_an_unknown_topic_exits_non_zero(settings_path: Path, topics_path: Path) -> None:
    result = invoke(settings_path, topics_path, "classifier", "set", "B", "--topic", "missing")

    assert result.exit_code == 1


def test_compare_reports_the_metrics_after_a_shadow_run(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200, json={"choices": [{"message": {"role": "assistant", "content": _VERDICT}}]}
            )
        return httpx.Response(200, json=_OPENALEX_PAGE)

    monkeypatch.setattr(
        cli,
        "_http_client",
        lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    invoke(
        settings_path, topics_path, "classifier", "set", "A", "--topic", TOPIC_ID, "--shadow", "B"
    )
    invoke(settings_path, topics_path, "classify", "--topic", TOPIC_ID)

    result = invoke(settings_path, topics_path, "compare-classifiers", TOPIC_ID)

    assert result.exit_code == 0, result.output
    assert "classifier_a (active) vs classifier_b (shadow)" in result.output
    assert "agreement rate" in result.output


def test_compare_without_shadow_verdicts_exits_non_zero(
    settings_path: Path, topics_path: Path
) -> None:
    result = invoke(settings_path, topics_path, "compare-classifiers", TOPIC_ID)

    assert result.exit_code == 1
    assert "No shadow verdicts stored" in result.output
