"""The shelf is the stored library in the shape the desk page already renders."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from research_agent.config import TopicSettings
from research_agent.desk.shelf import build_shelf, executive_summary_text, find_run
from research_agent.domain.analysis import (
    Claim,
    ClassificationResult,
    PaperAnalysis,
    ResearchGap,
    ResearchIdea,
    SupportedFinding,
    WeeklySynthesis,
)
from research_agent.domain.runs import RunSummary
from research_agent.domain.selection import SelectionDecision, SelectionPlan
from research_agent.reports.naming import report_filename
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from research_agent.storage.selections import SqliteSelectionRepository
from tests.unit.conftest import TOPIC_ID, candidate


def test_executive_summary_ignores_the_degradation_note() -> None:
    markdown = """
## Executive Summary

Named maps replaced grids this week.

> Degraded run: 1 recorded error(s).

## Most Important Developments
"""
    assert executive_summary_text(markdown) == "Named maps replaced grids this week."
    assert executive_summary_text("no heading here") is None


def test_build_shelf_uses_the_stored_week(connection: sqlite3.Connection, tmp_path: Path) -> None:
    runs = SqliteRunRepository(connection)
    record = runs.start(TOPIC_ID)
    runs.complete(
        record.id,
        RunSummary(
            candidates_discovered=12,
            papers_classified=4,
            papers_selected=1,
            deep_reads=1,
            models_used=["glm-test"],
        ),
        status="degraded",
    )
    paper_id = SqlitePaperRepository(connection).upsert(
        candidate(title="Language-Conditioned Topological Maps", doi="10.1000/topo")
    )
    results = SqliteResultRepository(connection)
    results.save_classification(
        record.id,
        ClassificationResult(
            paper_id=paper_id,
            classifier_name="semantic_screening",
            relevance="high",
            paper_type="method",
            action="deep_read",
            reason_short="on topic",
        ),
    )
    results.save_analysis(
        record.id,
        PaperAnalysis(
            paper_id=paper_id,
            research_problem="Grids forget a moved chair.",
            main_contribution="A named topological map.",
            method="Pose graph plus language notes.",
            main_results=["78% second-visit success"],
            key_claims=[
                Claim(text="Second-visit success was 78%.", source_section="Experiments", page=6)
            ],
            topic_relevance="This is the spatial memory the topic tracks.",
            model_provider="nvidia_nim",
            model_name="glm-test",
            prompt_version="paper_analysis.v1",
        ),
    )
    results.save_synthesis(
        record.id,
        TOPIC_ID,
        WeeklySynthesis(
            major_developments=[
                SupportedFinding(
                    text="Named memory showed up in the deep read.",
                    supporting_paper_ids=[paper_id],
                )
            ],
            model_provider="nvidia_nim",
            model_name="glm-test",
            prompt_version="weekly_synthesis.v1",
            history_periods=1,
        ),
        period_start=datetime(2026, 9, 18, tzinfo=UTC).date(),
        period_end=datetime(2026, 9, 28, tzinfo=UTC).date(),
    )
    results.save_gaps(
        record.id,
        TOPIC_ID,
        [
            ResearchGap(
                title="Unobserved layout change",
                description="No paper moves furniture while the robot is away.",
                supporting_paper_ids=[paper_id],
                model_provider="nvidia_nim",
                model_name="glm-test",
                prompt_version="research_gaps.v1",
            )
        ],
    )
    results.save_ideas(
        record.id,
        TOPIC_ID,
        [
            ResearchIdea(
                title="Move three objects",
                hypothesis="The lead disappears if the notes are stale.",
                motivation="The papers disagree.",
                supporting_paper_ids=[paper_id],
                identified_gap="Unobserved layout change",
                proposed_direction="Replay the second visit after a silent move.",
                evaluation_plan="Count collisions.",
                model_provider="nvidia_nim",
                model_name="glm-test",
                prompt_version="research_ideas.v1",
            )
        ],
    )
    SqliteSelectionRepository(connection).save(
        record.id,
        SelectionPlan(
            decisions=[
                SelectionDecision(
                    paper_id=paper_id,
                    rank=1,
                    selected=True,
                    action="deep_read",
                    reason="selected_deep_read",
                )
            ]
        ),
    )
    store = LocalArtifactStore(tmp_path)
    period_end = datetime(2026, 9, 28, tzinfo=UTC).date()
    store.write_text(
        TOPIC_ID,
        "reports",
        report_filename(period_end),
        "# Report\n\n## Executive Summary\n\nNamed maps won the week.\n\n> Degraded.\n\n## Next\n",
    )

    shelf = build_shelf(
        [TopicSettings(id=TOPIC_ID, name="Spatial Intelligence")],
        runs,
        results,
        SqlitePaperRepository(connection),
        SqliteSelectionRepository(connection),
        store,
    )

    assert shelf["live"] is True
    run = find_run(shelf, TOPIC_ID, record.id)
    assert run is not None
    assert run["status"] == "degraded"
    assert run["executiveSummary"] == "Named maps won the week."
    assert run["models"] == ["glm-test"]
    assert run["readingOrder"] == {"essential": [paper_id], "useful": [], "peripheral": []}
    papers = run["papers"]
    assert isinstance(papers, list)
    assert papers[0]["title"] == "Language-Conditioned Topological Maps"
    assert papers[0]["contribution"] == "A named topological map."
    assert papers[0]["claims"] == [
        {"text": "Second-visit success was 78%.", "section": "Experiments", "page": 6}
    ]
    gaps = run["gaps"]
    assert isinstance(gaps, list)
    assert gaps[0]["title"] == "Unobserved layout change"
    ideas = run["ideas"]
    assert isinstance(ideas, list)
    assert ideas[0]["direction"] == "Replay the second visit after a silent move."
    assert find_run(shelf, TOPIC_ID, "missing") is None
