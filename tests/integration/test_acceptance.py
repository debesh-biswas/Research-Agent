"""The MVP acceptance sweep (PRD section 19, TRD section 34).

One fully mocked stack, exercised for the properties the PRD promises: caching and idempotency,
resource limits, a complete run summary, a reproducible manifest, a consistent error taxonomy,
tolerance of a corrupt cache, and no credential anywhere in what a run writes.
"""

import asyncio
import json
import sqlite3
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest

from research_agent.domain.runs import ErrorCategory
from research_agent.observability.manifest import MANIFEST_VERSION
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.runs import SqliteRunRepository
from tests.integration.conftest import TOPIC_ID
from tests.integration.test_workflow_graph import (
    END,
    START,
    FakeParser,
    Handler,
    execute,
    handler,
    services,
    topic,
)

KEY = "nvapi-3f9Qz7LmT2xWv8pR4sKd6BhN1cYgE5jA0uZoI7"


def counted(**options: object) -> tuple[Handler, dict[str, int]]:
    """The standard transport, plus a tally of what each stage was asked to do."""
    calls: dict[str, int] = {}
    base = handler(**options)  # type: ignore[arg-type]

    def respond(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith(".pdf"):
            calls["download"] = calls.get("download", 0) + 1
        elif url.endswith("/chat/completions"):
            prompt = str(json.loads(request.content)["messages"]).lower()
            stage = (
                "screening"
                if "return relevance, relevance_score" in prompt
                else "synthesis"
                if "compare this week" in prompt
                else "gaps"
                if "identify unaddressed research questions" in prompt
                else "ideas"
                if "turn identified research gaps" in prompt
                else "prose"
                if "executive summary" in prompt
                else "analysis"
            )
            calls[stage] = calls.get(stage, 0) + 1
        else:
            calls["search"] = calls.get("search", 0) + 1
        return base(request)

    return respond, calls


def test_a_complete_run_satisfies_the_acceptance_criteria(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    respond, calls = counted()

    final = execute(services(connection, tmp_path, respond))

    assert final.status == "completed"
    assert final.report_path is not None and Path(final.report_path).is_file()
    report = Path(final.report_path).read_text(encoding="utf-8")
    for heading in ("## Executive Summary", "## Research Gaps", "## Sources", "## Run Provenance"):
        assert heading in report
    assert calls["analysis"] >= 1 and calls["synthesis"] == 1


def test_an_unchanged_rerun_repeats_no_expensive_work(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """Idempotency: a second run of the same week re-reads nothing and re-downloads nothing."""
    respond, calls = counted()
    execute(services(connection, tmp_path, respond))
    first = dict(calls)
    calls.clear()

    execute(services(connection, tmp_path, respond))

    assert first["analysis"] >= 1 and first["download"] >= 1
    assert calls.get("analysis", 0) == 0, "an unchanged paper is never analysed twice"
    assert calls.get("download", 0) == 0, "a stored PDF is never downloaded again"


def test_the_run_summary_is_complete(connection: sqlite3.Connection, tmp_path: Path) -> None:
    respond, _ = counted()

    final = execute(services(connection, tmp_path, respond))

    record = SqliteRunRepository(connection).get(final.run_id or "")
    assert record is not None and record.summary is not None
    summary = record.summary
    assert summary.candidates_discovered > 0
    assert summary.papers_classified > 0
    assert summary.papers_selected > 0
    assert summary.downloads_succeeded > 0
    assert summary.models_used, "the models that produced the analyses are recorded"
    assert record.duration_seconds is not None and record.duration_seconds >= 0
    assert record.completed_at is not None
    assert (record.active_classifier, record.shadow_classifier) == ("semantic_screening", None)


def test_the_manifest_records_the_inputs_and_no_secret(
    connection: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_MODELS__NIM__API_KEY", KEY)
    respond, _ = counted()

    final = execute(services(connection, tmp_path, respond))

    store = LocalArtifactStore(tmp_path / "data")
    name = f"{final.run_id}-manifest.json"
    assert store.exists(TOPIC_ID, "runs", name)
    raw = store.read_text(TOPIC_ID, "runs", name)
    manifest = json.loads(raw)
    assert manifest["manifest_version"] == MANIFEST_VERSION
    assert manifest["run"]["id"] == final.run_id
    assert manifest["topic"]["lookback_days"] == topic().lookback_days
    assert manifest["sources_enabled"] == ["openalex"]
    assert manifest["screening"] == {"service": "semantic_screening"}
    assert manifest["prompt_versions"]["paper_analysis"] == "paper_analysis.v1"
    assert manifest["counts"]["classified"] >= 1
    assert KEY not in raw and "api_key" not in raw.lower()


def test_resource_limits_are_respected(connection: sqlite3.Connection, tmp_path: Path) -> None:
    respond, calls = counted()
    workflow = services(connection, tmp_path, respond)
    bounded = topic().model_copy(
        update={
            "limits": topic().limits.model_copy(
                update={
                    "max_candidates": 2,
                    "max_classified": 1,
                    "max_downloads": 1,
                    "max_deep_reads": 1,
                }
            )
        }
    )

    final = execute(replace(workflow, topic=bounded))

    assert len(final.candidates) <= 2
    assert len(final.classifications) <= 1
    assert calls["download"] <= 1
    assert len(final.analyzed_ids) <= 1


def test_every_recorded_error_uses_the_documented_taxonomy(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    respond, _ = counted(pdf=False)

    final = execute(services(connection, tmp_path, respond))

    errors = SqliteRunRepository(connection).errors_for(final.run_id or "")
    assert errors, "a failed download is recorded, not swallowed"
    allowed = set(ErrorCategory.__args__)  # type: ignore[attr-defined]
    assert {error.category for error in errors} <= allowed
    assert all(error.node for error in errors)
    assert final.status == "degraded"


def test_a_corrupt_parsed_artifact_degrades_to_abstract_only(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    respond, _ = counted()
    first = execute(services(connection, tmp_path, respond))
    store = LocalArtifactStore(tmp_path / "data")
    for paper_id in first.parsed_paths:
        store.write_text(TOPIC_ID, "parsed", f"{paper_id}.json", "{not json")
    SqlitePaperRepository(connection)  # the stored rows stay; only the artifact is broken

    second = execute(services(connection, tmp_path, respond, parser=FakeParser(), planner=False))

    assert second.report_path is not None, "a corrupt cache must not end the run"
    assert second.status in ("completed", "degraded")


def test_an_interrupted_run_does_not_block_the_next_one(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    runs = SqliteRunRepository(connection)
    abandoned = runs.start(TOPIC_ID, "A")
    respond, _ = counted()

    final = execute(services(connection, tmp_path, respond))

    assert final.run_id != abandoned.id
    assert final.report_path is not None
    assert runs.get(abandoned.id) is not None, "the abandoned run is kept for diagnosis"


def test_nothing_a_run_writes_contains_a_credential(
    connection: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RESEARCH_AGENT_MODELS__NIM__API_KEY", KEY)
    respond, _ = counted()

    execute(services(connection, tmp_path, respond))

    written = [path for path in (tmp_path / "data").rglob("*") if path.is_file()]
    assert written, "the run wrote artifacts"
    for path in written:
        if path.suffix in {".md", ".json", ".txt"}:
            assert KEY not in path.read_text(encoding="utf-8", errors="ignore"), path


def test_report_references_are_deterministic(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """The same run must render the same references, whenever the report is built."""
    respond, _ = counted()
    workflow = services(connection, tmp_path, respond)
    final = execute(workflow)
    assert final.report_path is not None and final.run_id is not None
    original = Path(final.report_path).read_text(encoding="utf-8")
    record = SqliteRunRepository(connection).get(final.run_id)
    assert record is not None

    rebuilt = asyncio.run(
        workflow.reports.generate(topic(), record, final.selected_ids, START, END)
    )

    assert rebuilt.path == final.report_path
    rerun = Path(rebuilt.path).read_text(encoding="utf-8")
    assert _sources(original) == _sources(rerun)
    assert _sources(original), "the report cites the papers it read"


def test_a_rerun_of_an_unchanged_week_reports_an_empty_week(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    """The deliberate consequence of caching: nothing new to read means nothing new to report."""
    respond, _ = counted()
    execute(services(connection, tmp_path, respond))

    second = execute(services(connection, tmp_path, respond))

    assert second.selected_ids == [] and second.empty_week is True
    assert second.report_path is not None
    assert "No paper met this period" in Path(second.report_path).read_text(encoding="utf-8")


def _sources(report: str) -> list[str]:
    section = report.split("## Sources")[1].split("## Run Provenance")[0]
    return sorted(line for line in section.splitlines() if line.startswith("- "))


def test_the_reporting_period_matches_the_run(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    respond, _ = counted()

    final = execute(services(connection, tmp_path, respond))

    assert (final.period_start, final.period_end) == (START, END)
    assert final.report_path is not None
    assert f"{START.isoformat()} to {END.isoformat()}" in Path(final.report_path).read_text(
        encoding="utf-8"
    )
    assert isinstance(final.period_end, date)
