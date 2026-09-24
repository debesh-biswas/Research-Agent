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
            for table in ("runs", "papers", "classifications", "selections")
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
    assert counts(tmp_path) == {
        "runs": 1,
        "papers": 2,
        "classifications": 2,
        "selections": 2,
    }


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
    assert counts(tmp_path) == {
        "runs": 0,
        "papers": 0,
        "classifications": 0,
        "selections": 0,
    }


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
    assert counts(tmp_path) == {
        "runs": 1,
        "papers": 0,
        "classifications": 0,
        "selections": 0,
    }


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


_VERDICT = (
    '{"relevance": "medium", "relevance_score": 0.5, "paper_type": "method", '
    '"action": "summarize", "confidence": 0.7, "reason_short": "related work"}'
)


@pytest.fixture
def shadow_topics_path(tmp_path: Path) -> Path:
    path = tmp_path / "topics.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "topics": [
                    {
                        "id": TOPIC_ID,
                        "name": "Spatial Intelligence",
                        "keywords": ["embodied navigation"],
                        "classifier": {"active": "A", "shadow": "B"},
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


def _routing_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/chat/completions"):
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": _VERDICT}}]}
        )
    return httpx.Response(200, json=_OPENALEX_PAGE)


def test_shadow_mode_stores_both_verdicts_with_one_active(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, shadow_topics_path: Path, tmp_path: Path
) -> None:
    result = run_classify(monkeypatch, settings_path, shadow_topics_path, _routing_handler)

    assert result.exit_code == 0, result.output
    assert "shadow classifier B: 2 verdict(s)" in result.output
    assert counts(tmp_path) == {
        "runs": 1,
        "papers": 2,
        "classifications": 4,
        "selections": 2,
    }

    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        rows = connection.execute(
            "SELECT classifier_name, is_active FROM classifications ORDER BY classifier_name"
        ).fetchall()
    finally:
        connection.close()
    assert sorted(rows) == [
        ("classifier_a", 1),
        ("classifier_a", 1),
        ("classifier_b", 0),
        ("classifier_b", 0),
    ]


def test_a_failing_shadow_model_leaves_the_active_verdicts_intact(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, shadow_topics_path: Path, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(503)
        return httpx.Response(200, json=_OPENALEX_PAGE)

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    result = run_classify(monkeypatch, settings_path, shadow_topics_path, handler)

    assert result.exit_code == 0, result.output
    assert "2 verdict(s)" in result.output
    assert "shadow classifier B: 0 verdict(s)" in result.output
    assert counts(tmp_path) == {
        "runs": 1,
        "papers": 2,
        "classifications": 2,
        "selections": 2,
    }


def test_the_selection_summary_and_reasons_are_printed(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    result = run_classify(
        monkeypatch,
        settings_path,
        topics_path,
        lambda request: httpx.Response(200, json=_OPENALEX_PAGE),
    )

    assert result.exit_code == 0, result.output
    assert "selected 1 of 2: 1 deep read, 0 summarize." in result.output
    assert "action_ignore" in result.output

    connection = sqlite3.connect(tmp_path / "data" / "research_agent.db")
    try:
        rows = connection.execute(
            "SELECT rank, selected, reason FROM selections ORDER BY rank"
        ).fetchall()
        selected = connection.execute("SELECT papers_selected FROM runs").fetchone()[0]
    finally:
        connection.close()
    assert [(row[0], row[1], row[2]) for row in rows] == [
        (1, 1, "selected_deep_read"),
        (2, 0, "action_ignore"),
    ]
    assert selected == 1


def test_an_already_analyzed_paper_is_skipped_until_reanalyze(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, topics_path: Path, tmp_path: Path
) -> None:
    handler = lambda request: httpx.Response(200, json=_OPENALEX_PAGE)  # noqa: E731
    run_classify(monkeypatch, settings_path, topics_path, handler)

    database = tmp_path / "data" / "research_agent.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE papers SET first_analyzed_at = '2026-09-01T00:00:00+00:00', "
            "last_analyzed_at = '2026-09-01T00:00:00+00:00', analyzed_hash = content_hash"
        )
        connection.commit()
    finally:
        connection.close()

    skipped = run_classify(monkeypatch, settings_path, topics_path, handler)
    assert "selected 0 of 2" in skipped.output
    assert "already_analyzed" in skipped.output

    forced = run_classify(monkeypatch, settings_path, topics_path, handler, "--reanalyze")
    assert "selected 1 of 2" in forced.output


def test_the_deep_read_limit_bounds_the_selection(
    monkeypatch: pytest.MonkeyPatch, settings_path: Path, tmp_path: Path
) -> None:
    topics = tmp_path / "limited.yaml"
    topics.write_text(
        yaml.safe_dump(
            {
                "topics": [
                    {
                        "id": TOPIC_ID,
                        "name": "Spatial Intelligence",
                        "keywords": ["embodied navigation"],
                        "limits": {"max_downloads": 1, "max_deep_reads": 1},
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
    titles = [
        "Spatial Intelligence for Embodied Navigation",
        "Mapping and Memory in Spatial Intelligence",
        "Embodied Navigation with Scene Graphs",
        "Spatial Intelligence Benchmarks for Household Robots",
    ]
    page = {
        "meta": {"next_cursor": None},
        "results": [
            {
                "id": f"https://openalex.org/W{index}",
                "display_name": title,
                "doi": f"https://doi.org/10.1234/paper{index}",
                "publication_date": "2026-09-18",
                "authorships": [{"author": {"display_name": f"Author {index}"}}],
            }
            for index, title in enumerate(titles)
        ],
    }

    result = run_classify(
        monkeypatch, settings_path, topics, lambda request: httpx.Response(200, json=page)
    )

    assert result.exit_code == 0, result.output
    assert "selected 1 of 4" in result.output
    assert "limit_reached" in result.output
