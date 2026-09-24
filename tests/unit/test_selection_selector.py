import random

from research_agent.config import ResourceLimits, SelectionSettings
from research_agent.domain.analysis import ClassificationResult
from research_agent.domain.selection import SelectionPlan
from research_agent.selection.selector import select

LIMITS = ResourceLimits(max_downloads=50, max_deep_reads=15)


def verdict(
    paper_id: str,
    action: str = "deep_read",
    relevance: str = "high",
    score: float | None = 0.9,
    confidence: float | None = 0.8,
) -> ClassificationResult:
    return ClassificationResult(
        paper_id=paper_id,
        classifier_name="classifier_a",
        relevance=relevance,  # type: ignore[arg-type]
        relevance_score=score,
        paper_type="method",
        action=action,  # type: ignore[arg-type]
        confidence=confidence,
    )


def reasons(plan: SelectionPlan) -> dict[str, str]:
    return {decision.paper_id: decision.reason for decision in plan.decisions}


def test_every_classified_paper_gets_exactly_one_decision() -> None:
    verdicts = [verdict("p1"), verdict("p2", action="ignore"), verdict("p3", score=0.1)]

    plan = select(verdicts, LIMITS)

    assert len(plan.decisions) == 3
    assert len({decision.paper_id for decision in plan.decisions}) == 3
    assert [decision.rank for decision in plan.decisions] == [1, 2, 3]


def test_deep_reads_outrank_summaries_which_outrank_ignores() -> None:
    verdicts = [
        verdict("c", action="ignore", relevance="low", score=0.99),
        verdict("b", action="summarize", relevance="medium", score=0.5),
        verdict("a", action="deep_read", score=0.4),
    ]

    plan = select(verdicts, LIMITS)

    assert [decision.paper_id for decision in plan.decisions] == ["a", "b", "c"]


def test_ordering_is_stable_however_the_input_is_shuffled() -> None:
    verdicts = [verdict(f"p{index}", score=0.9 - index / 100) for index in range(10)]
    expected = [decision.paper_id for decision in select(verdicts, LIMITS).decisions]

    for seed in range(5):
        shuffled = verdicts[:]
        random.Random(seed).shuffle(shuffled)
        assert [d.paper_id for d in select(shuffled, LIMITS).decisions] == expected


def test_identical_scores_break_the_tie_on_paper_id() -> None:
    plan = select([verdict("zebra"), verdict("alpha"), verdict("mid")], LIMITS)

    assert [decision.paper_id for decision in plan.decisions] == ["alpha", "mid", "zebra"]


def test_an_ignored_paper_is_never_selected() -> None:
    plan = select([verdict("p1", action="ignore")], LIMITS)

    assert plan.selected_ids == []
    assert reasons(plan)["p1"] == "action_ignore"


def test_a_sub_threshold_score_is_dropped_with_its_reason() -> None:
    plan = select([verdict("p1", score=0.2)], LIMITS, SelectionSettings(min_relevance_score=0.3))

    assert reasons(plan)["p1"] == "below_threshold"


def test_a_missing_score_counts_as_zero() -> None:
    plan = select([verdict("p1", score=None)], LIMITS)

    assert reasons(plan)["p1"] == "below_threshold"


def test_require_action_can_be_turned_off() -> None:
    plan = select([verdict("p1", action="ignore")], LIMITS, SelectionSettings(require_action=False))

    assert plan.selected_ids == ["p1"]


def test_the_deep_read_cap_is_never_exceeded() -> None:
    verdicts = [verdict(f"p{index:02d}") for index in range(20)]

    plan = select(verdicts, ResourceLimits(max_downloads=50, max_deep_reads=3))

    assert len(plan.deep_reads) == 3
    # The rest are downgraded rather than dropped, and the downgrade stays visible.
    assert len(plan.summaries) == 17


def test_the_download_cap_bounds_the_whole_selection() -> None:
    verdicts = [verdict(f"p{index:02d}") for index in range(20)]

    plan = select(verdicts, ResourceLimits(max_downloads=5, max_deep_reads=2))

    assert len(plan.selected_ids) == 5
    assert sum(1 for d in plan.decisions if d.reason == "limit_reached") == 15


def test_a_zero_limit_selects_nothing_but_still_explains_itself() -> None:
    plan = select([verdict("p1")], ResourceLimits(max_downloads=0, max_deep_reads=0))

    assert plan.selected_ids == []
    assert reasons(plan)["p1"] == "limit_reached"


def test_an_already_analyzed_paper_is_skipped() -> None:
    plan = select([verdict("p1"), verdict("p2")], LIMITS, analyzed={"p1"})

    assert plan.selected_ids == ["p2"]
    assert reasons(plan)["p1"] == "already_analyzed"


def test_reanalyze_brings_an_analyzed_paper_back() -> None:
    plan = select([verdict("p1")], LIMITS, analyzed={"p1"}, reanalyze=True)

    assert plan.selected_ids == ["p1"]


def test_an_empty_verdict_list_is_an_empty_plan() -> None:
    plan = select([], LIMITS)

    assert (plan.decisions, plan.selected_ids, plan.deep_reads) == ([], [], [])


def test_the_same_inputs_produce_an_identical_plan_twice() -> None:
    verdicts = [verdict("p1"), verdict("p2", action="summarize"), verdict("p3", action="ignore")]

    assert select(verdicts, LIMITS) == select(verdicts, LIMITS)
