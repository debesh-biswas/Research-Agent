"""Classifier comparison metrics (TRD section 47).

Pure functions over stored verdicts: no inference, no network, so the same rows always produce the
same report.
"""

from collections import Counter
from collections.abc import Iterable

from pydantic import Field

from research_agent.config import StrictModel
from research_agent.domain.analysis import ClassificationResult


class ClassifierComparison(StrictModel):
    """Agreement and distribution metrics over papers both classifiers judged."""

    active_name: str
    shadow_name: str
    compared: int = Field(ge=0)
    agreements: int = Field(ge=0)
    disagreements: int = Field(ge=0)
    agreement_rate: float = Field(ge=0, le=1)
    average_latency_ms: dict[str, float] = Field(default_factory=dict)
    average_confidence: dict[str, float] = Field(default_factory=dict)
    action_distribution: dict[str, dict[str, int]] = Field(default_factory=dict)
    relevance_distribution: dict[str, dict[str, int]] = Field(default_factory=dict)


def compare(
    active: list[ClassificationResult], shadow: list[ClassificationResult]
) -> ClassifierComparison:
    """Pair verdicts by paper and measure how often the two classifiers route a paper the same way.

    Papers only one classifier judged are excluded: a comparison of different sets is not a
    comparison. Agreement is on `action`, because that is what actually controls the run.
    """
    shadow_by_paper = {result.paper_id: result for result in shadow}
    pairs = [
        (result, shadow_by_paper[result.paper_id])
        for result in active
        if result.paper_id in shadow_by_paper
    ]
    agreements = sum(1 for left, right in pairs if left.action == right.action)
    active_name = active[0].classifier_name if active else "none"
    shadow_name = shadow[0].classifier_name if shadow else "none"

    return ClassifierComparison(
        active_name=active_name,
        shadow_name=shadow_name,
        compared=len(pairs),
        agreements=agreements,
        disagreements=len(pairs) - agreements,
        agreement_rate=agreements / len(pairs) if pairs else 0.0,
        average_latency_ms={
            active_name: _mean([result.latency_ms for result, _ in pairs]),
            shadow_name: _mean([result.latency_ms for _, result in pairs]),
        },
        average_confidence={
            active_name: _mean([result.confidence for result, _ in pairs]),
            shadow_name: _mean([result.confidence for _, result in pairs]),
        },
        action_distribution={
            active_name: _counts(result.action for result, _ in pairs),
            shadow_name: _counts(result.action for _, result in pairs),
        },
        relevance_distribution={
            active_name: _counts(result.relevance for result, _ in pairs),
            shadow_name: _counts(result.relevance for _, result in pairs),
        },
    )


def render(comparison: ClassifierComparison) -> str:
    """Format a comparison for a terminal, with keys in a stable order."""
    lines = [
        f"compared {comparison.compared} paper(s): "
        f"{comparison.active_name} (active) vs {comparison.shadow_name} (shadow)",
        f"agreement rate {comparison.agreement_rate:.2f} "
        f"({comparison.agreements} agree, {comparison.disagreements} disagree)",
    ]
    for name in (comparison.active_name, comparison.shadow_name):
        lines.append(
            f"{name}: avg latency {comparison.average_latency_ms.get(name, 0.0):.0f}ms, "
            f"avg confidence {comparison.average_confidence.get(name, 0.0):.2f}, "
            f"actions {_inline(comparison.action_distribution.get(name, {}))}, "
            f"relevance {_inline(comparison.relevance_distribution.get(name, {}))}"
        )
    return "\n".join(lines)


def _mean(values: list[int | None] | list[float | None]) -> float:
    present = [float(value) for value in values if value is not None]
    return round(sum(present) / len(present), 4) if present else 0.0


def _counts(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _inline(counts: dict[str, int]) -> str:
    return "{" + ", ".join(f"{key} {value}" for key, value in sorted(counts.items())) + "}"
