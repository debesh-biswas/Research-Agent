"""Turn active-classifier verdicts into a bounded, reproducible reading set.

Pure: no clock, no database, no network. The same verdicts and the same limits always produce the
same plan, which is what makes a run reconstructable later.
"""

from collections.abc import Collection, Mapping
from datetime import date

from research_agent.config import ResourceLimits, SelectionSettings
from research_agent.domain.analysis import ClassificationResult
from research_agent.domain.papers import PaperCandidate
from research_agent.domain.selection import SelectionDecision, SelectionPlan, SelectionReason
from research_agent.selection.quality import ranking_score

_ACTION_RANK = {"deep_read": 0, "summarize": 1, "ignore": 2}
_RELEVANCE_RANK = {"high": 0, "medium": 1, "low": 2}


def _sort_key(
    result: ClassificationResult,
    papers: Mapping[str, PaperCandidate],
    settings: SelectionSettings,
    as_of: date,
) -> tuple[int, float, int, float, float, str]:
    """A total order. The last key is an identifier, so ties can never reorder between runs."""
    return (
        _ACTION_RANK[result.action],
        -ranking_score(result.relevance_score, papers.get(result.paper_id), settings, as_of),
        _RELEVANCE_RANK[result.relevance],
        -(result.relevance_score or 0.0),
        -(result.confidence or 0.0),
        result.paper_id,
    )


def select(
    verdicts: list[ClassificationResult],
    limits: ResourceLimits,
    settings: SelectionSettings | None = None,
    analyzed: Collection[str] = (),
    reanalyze: bool = False,
    papers: Mapping[str, PaperCandidate] | None = None,
    as_of: date | None = None,
) -> SelectionPlan:
    """Rank, filter, and cap verdicts; every input gets exactly one recorded decision."""
    options = settings or SelectionSettings()
    paper_map = papers or {}
    ranking_date = as_of or date.today()
    already = set() if reanalyze else set(analyzed)
    deep_reads = 0
    selected = 0
    decisions: list[SelectionDecision] = []

    ordered = sorted(
        verdicts,
        key=lambda result: _sort_key(result, paper_map, options, ranking_date),
    )
    for rank, result in enumerate(ordered, start=1):
        reason = _reject(result, options, already)
        if reason is None:
            # A deep-read paper past the deep-read cap is downgraded rather than dropped; the
            # decision keeps both its action and its reason, so the downgrade stays visible.
            if result.action == "deep_read" and deep_reads < limits.max_deep_reads:
                reason, deep_reads = "selected_deep_read", deep_reads + 1
            elif selected < limits.max_downloads:
                reason = "selected_summarize"
            else:
                reason = "limit_reached"
            if reason != "limit_reached":
                selected += 1
        decisions.append(
            SelectionDecision(
                paper_id=result.paper_id,
                rank=rank,
                selected=reason in ("selected_deep_read", "selected_summarize"),
                action=result.action,
                reason=reason,
            )
        )
    return SelectionPlan(decisions=decisions)


def _reject(
    result: ClassificationResult, settings: SelectionSettings, already: set[str]
) -> SelectionReason | None:
    """The reasons a paper is never eligible, checked before any limit is spent on it."""
    if settings.require_action and result.action == "ignore":
        return "action_ignore"
    if (result.relevance_score or 0.0) < settings.min_relevance_score:
        return "below_threshold"
    if result.paper_id in already:
        return "already_analyzed"
    return None
