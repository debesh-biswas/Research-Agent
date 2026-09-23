import pytest

from research_agent.classifiers.comparison import compare, render
from research_agent.domain.analysis import ClassificationResult


def verdict(
    paper_id: str,
    name: str = "classifier_a",
    action: str = "deep_read",
    relevance: str = "high",
    latency_ms: int | None = 10,
    confidence: float | None = 0.8,
) -> ClassificationResult:
    return ClassificationResult(
        paper_id=paper_id,
        classifier_name=name,
        relevance=relevance,  # type: ignore[arg-type]
        paper_type="method",
        action=action,  # type: ignore[arg-type]
        confidence=confidence,
        latency_ms=latency_ms,
    )


def test_identical_verdicts_agree_completely() -> None:
    active = [verdict("p1"), verdict("p2")]
    shadow = [verdict("p1", "classifier_b"), verdict("p2", "classifier_b")]

    comparison = compare(active, shadow)

    assert (comparison.compared, comparison.agreements, comparison.disagreements) == (2, 2, 0)
    assert comparison.agreement_rate == 1.0


def test_a_different_action_is_a_disagreement() -> None:
    comparison = compare(
        [verdict("p1"), verdict("p2")],
        [verdict("p1", "classifier_b"), verdict("p2", "classifier_b", action="ignore")],
    )

    assert (comparison.agreements, comparison.disagreements) == (1, 1)
    assert comparison.agreement_rate == pytest.approx(0.5)


def test_papers_only_one_classifier_judged_are_excluded() -> None:
    comparison = compare([verdict("p1"), verdict("p2")], [verdict("p1", "classifier_b")])

    assert comparison.compared == 1


def test_no_shared_papers_yields_an_empty_comparison() -> None:
    comparison = compare([verdict("p1")], [verdict("p2", "classifier_b")])

    assert (comparison.compared, comparison.agreement_rate) == (0, 0.0)


def test_empty_input_is_reported_rather_than_raising() -> None:
    comparison = compare([], [])

    assert (comparison.active_name, comparison.shadow_name, comparison.compared) == (
        "none",
        "none",
        0,
    )


def test_latency_and_confidence_are_averaged_per_classifier() -> None:
    comparison = compare(
        [verdict("p1", latency_ms=10), verdict("p2", latency_ms=20)],
        [
            verdict("p1", "classifier_b", latency_ms=100, confidence=0.4),
            verdict("p2", "classifier_b", latency_ms=200, confidence=0.6),
        ],
    )

    assert comparison.average_latency_ms == {"classifier_a": 15.0, "classifier_b": 150.0}
    assert comparison.average_confidence["classifier_b"] == pytest.approx(0.5)


def test_missing_latency_and_confidence_do_not_skew_the_average() -> None:
    comparison = compare(
        [verdict("p1", latency_ms=None, confidence=None), verdict("p2", latency_ms=20)],
        [verdict("p1", "classifier_b"), verdict("p2", "classifier_b")],
    )

    assert comparison.average_latency_ms["classifier_a"] == 20.0
    assert comparison.average_confidence["classifier_a"] == pytest.approx(0.8)


def test_distributions_count_actions_and_relevance() -> None:
    comparison = compare(
        [verdict("p1"), verdict("p2", action="ignore", relevance="low")],
        [verdict("p1", "classifier_b"), verdict("p2", "classifier_b")],
    )

    assert comparison.action_distribution["classifier_a"] == {"deep_read": 1, "ignore": 1}
    assert comparison.relevance_distribution["classifier_a"] == {"high": 1, "low": 1}


def test_rendering_is_deterministic_and_names_both_classifiers() -> None:
    comparison = compare([verdict("p1")], [verdict("p1", "classifier_b")])

    text = render(comparison)

    assert text == render(comparison)
    assert "classifier_a (active) vs classifier_b (shadow)" in text
    assert "agreement rate 1.00" in text
