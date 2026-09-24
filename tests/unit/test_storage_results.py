import json
import sqlite3
from datetime import date

from research_agent.domain.analysis import (
    Claim,
    ClassificationResult,
    PaperAnalysis,
    ResearchGap,
    ResearchIdea,
    WeeklySynthesis,
)
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from tests.unit.conftest import TOPIC_ID, candidate


def _context(connection: sqlite3.Connection) -> tuple[SqliteResultRepository, str, str]:
    run = SqliteRunRepository(connection).start(TOPIC_ID)
    paper_id = SqlitePaperRepository(connection).upsert(candidate(doi="10.1234/abcd"))
    return SqliteResultRepository(connection), run.id, paper_id


def _classification(paper_id: str, name: str = "classifier_a") -> ClassificationResult:
    return ClassificationResult(
        paper_id=paper_id,
        classifier_name=name,
        relevance="high",
        relevance_score=0.91,
        paper_type="method",
        action="deep_read",
        confidence=0.8,
        reason_short="matches embodied spatial reasoning",
        latency_ms=42,
    )


def test_classifications_round_trip_with_shadow_results(connection: sqlite3.Connection) -> None:
    repository, run_id, paper_id = _context(connection)
    active = _classification(paper_id)
    shadow = _classification(paper_id, name="classifier_b")

    repository.save_classification(run_id, active, raw_response={"label": "high"})
    repository.save_classification(run_id, shadow, is_active=False)

    assert repository.classifications_for(run_id) == [active, shadow]
    assert repository.classifications_for(run_id, active_only=True) == [active]


def test_analysis_round_trips_and_returns_the_newest(connection: sqlite3.Connection) -> None:
    repository, run_id, paper_id = _context(connection)
    analysis = PaperAnalysis(
        paper_id=paper_id,
        research_problem="Agents cannot reason about unseen rooms.",
        main_contribution="A spatial memory module.",
        method="Transformer with a persistent map.",
        datasets=["HM3D"],
        benchmarks=["ObjectNav"],
        main_results=["+7 SPL over the baseline"],
        key_claims=[Claim(text="Memory improves navigation", source_section="5.2", page=7)],
        topic_relevance="Directly on topic.",
        model_provider="local",
        model_name="qwen",
    )
    repository.save_analysis(run_id, analysis)
    newest = analysis.model_copy(update={"main_contribution": "A revised module."})
    repository.save_analysis(run_id, newest)

    assert repository.analysis_for(paper_id) == newest
    assert repository.analysis_for("doi_missing") is None


def test_recent_syntheses_returns_the_history_window(connection: sqlite3.Connection) -> None:
    repository, run_id, _ = _context(connection)
    for week in range(1, 7):
        repository.save_synthesis(
            run_id,
            TOPIC_ID,
            WeeklySynthesis(major_developments=[f"week {week}"]),
            period_start=date(2026, 8, week),
            period_end=date(2026, 8, week + 1),
        )

    recent = repository.recent_syntheses(TOPIC_ID)

    assert [synthesis.major_developments[0] for synthesis in recent] == [
        "week 6",
        "week 5",
        "week 4",
        "week 3",
    ]
    assert repository.recent_syntheses("other_topic") == []


def test_gaps_and_ideas_round_trip(connection: sqlite3.Connection) -> None:
    repository, run_id, paper_id = _context(connection)
    gaps = [
        ResearchGap(
            title="No long-horizon benchmark",
            description="Existing benchmarks stop at 50 steps.",
            supporting_paper_ids=[paper_id],
            confidence=0.6,
        )
    ]
    ideas = [
        ResearchIdea(
            title="Persistent map benchmark",
            hypothesis="Longer horizons expose memory failures.",
            motivation="Current scores saturate.",
            supporting_paper_ids=[paper_id],
            identified_gap="No long-horizon benchmark",
            proposed_direction="Extend ObjectNav episodes.",
            evaluation_plan="Compare SPL across horizons.",
            risks=["Compute cost"],
        )
    ]

    repository.save_gaps(run_id, TOPIC_ID, gaps)
    repository.save_ideas(run_id, TOPIC_ID, ideas)

    assert repository.gaps_for(run_id) == gaps
    assert repository.ideas_for(run_id) == ideas
    assert repository.gaps_for("other_run") == []


def test_classifier_a_provenance_survives_as_the_raw_response(
    connection: sqlite3.Connection,
) -> None:
    repository, run_id, paper_id = _context(connection)
    provenance = {
        "version": "classifier_a.v1",
        "lexical_score": 0.75,
        "embedding_score": None,
        "embedding_weight": 0.0,
        "matched_terms": ["spatial intelligence"],
    }

    repository.save_classification(run_id, _classification(paper_id), raw_response=provenance)

    stored = connection.execute("SELECT raw_response_json FROM classifications").fetchone()
    assert json.loads(stored["raw_response_json"]) == provenance


def test_classification_pairs_split_active_from_shadow(connection: sqlite3.Connection) -> None:
    repository, run_id, paper_id = _context(connection)
    active = _classification(paper_id)
    shadow = _classification(paper_id, name="classifier_b")
    repository.save_classification(run_id, active)
    repository.save_classification(run_id, shadow, is_active=False)

    assert repository.classification_pairs(TOPIC_ID) == ([active], [shadow])


def test_classification_pairs_are_limited_to_recent_runs(connection: sqlite3.Connection) -> None:
    repository, first_run, paper_id = _context(connection)
    repository.save_classification(first_run, _classification(paper_id))
    second_run = SqliteRunRepository(connection).start(TOPIC_ID).id
    repository.save_classification(second_run, _classification(paper_id, name="classifier_b"))

    active, _ = repository.classification_pairs(TOPIC_ID, limit=1)

    assert [result.classifier_name for result in active] == ["classifier_b"]


def test_classification_pairs_ignore_other_topics(connection: sqlite3.Connection) -> None:
    repository, run_id, paper_id = _context(connection)
    repository.save_classification(run_id, _classification(paper_id))

    assert repository.classification_pairs("another_topic") == ([], [])
