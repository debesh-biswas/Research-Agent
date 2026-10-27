"""Deterministic assembly of the weekly report (PRD section 13).

Everything here is a pure function of stored records, so the same run always renders the same
document. The only model-written part, the executive summary, is passed in and is optional.
"""

from datetime import date

from pydantic import Field

from research_agent.config import StrictModel, TopicSettings
from research_agent.domain.analysis import (
    ClassificationResult,
    PaperAnalysis,
    ResearchGap,
    ResearchIdea,
    SupportedFinding,
    WeeklySynthesis,
)
from research_agent.domain.papers import PaperCandidate
from research_agent.domain.runs import ErrorRecord, RunRecord
from research_agent.utils.markdown import block, inline

_DOI_BASE = "https://doi.org/"
_ARXIV_BASE = "https://arxiv.org/abs/"

# Reading order (PRD section 13): the classifier's own action and relevance decide the tier, so the
# order is reproducible rather than a second judgement.
_ESSENTIAL = ("deep_read",)
_USEFUL = ("summarize",)


class ReportInputs(StrictModel):
    """Every stored record one report is built from."""

    topic: TopicSettings
    run: RunRecord
    period_start: date
    period_end: date
    papers: dict[str, PaperCandidate] = Field(default_factory=dict)
    analyses: list[PaperAnalysis] = Field(default_factory=list)
    classifications: list[ClassificationResult] = Field(default_factory=list)
    synthesis: WeeklySynthesis | None = None
    gaps: list[ResearchGap] = Field(default_factory=list)
    ideas: list[ResearchIdea] = Field(default_factory=list)
    errors: list[ErrorRecord] = Field(default_factory=list)


def build_report(inputs: ReportInputs, executive_summary: str | None = None) -> str:
    """Render the full report, or the empty-week report when nothing was analysed."""
    lines = [
        "# Weekly Research Intelligence Report",
        "",
        "## Topic",
        "",
        f"{inline(inputs.topic.name)} (`{inputs.topic.id}`)",
        "",
        "## Reporting Period",
        "",
        f"{inputs.period_start.isoformat()} to {inputs.period_end.isoformat()}",
    ]
    lines.extend(_summary(inputs, executive_summary))
    if inputs.analyses:
        lines.extend(_findings(inputs))
        lines.extend(_papers(inputs))
        lines.extend(_reading_order(inputs))
    lines.extend(_ideation(inputs))
    lines.extend(_sources(inputs))
    lines.extend(_provenance(inputs))
    return "\n".join(lines).rstrip() + "\n"


def _summary(inputs: ReportInputs, executive_summary: str | None) -> list[str]:
    lines = ["", "## Executive Summary", ""]
    if not inputs.analyses:
        lines.append(
            "No paper met this period's selection criteria, so there is nothing to report beyond "
            "the run record below. The topic's configuration and sources are unchanged."
        )
        return lines
    if executive_summary:
        lines.append(block(executive_summary))
    else:
        # The model-written paragraph is optional; the report must still stand without it.
        lines.append(
            f"{len(inputs.analyses)} paper(s) were analysed for {inline(inputs.topic.name)} in "
            f"this period. No model-written summary was available, so the sections below are the "
            f"report's own record of what changed."
        )
    if _degraded(inputs):
        lines.extend(
            [
                "",
                f"> Degraded run: {len(inputs.errors)} recorded error(s), "
                f"status `{inputs.run.status}`. Sections may be incomplete; see Run Provenance.",
            ]
        )
    abstract_only = [analysis for analysis in inputs.analyses if analysis.abstract_only]
    if abstract_only:
        lines.extend(
            [
                "",
                f"> {len(abstract_only)} of {len(inputs.analyses)} analyses are abstract-only, "
                "because no PDF could be acquired or parsed for them.",
            ]
        )
    return lines


def _findings(inputs: ReportInputs) -> list[str]:
    synthesis = inputs.synthesis
    lines: list[str] = []
    if synthesis is None:
        return [
            "",
            "## Most Important Developments",
            "",
            "No synthesis was produced for this period, so cross-paper findings are unavailable.",
        ]
    lines.extend(_findings_section("Most Important Developments", synthesis.major_developments))
    lines.extend(_findings_section("Emerging Research Directions", synthesis.emerging_directions))
    lines.extend(
        _findings_section("Methods Gaining Attention", synthesis.methods_gaining_attention)
    )
    lines.extend(
        _list_section(
            "New Datasets / Benchmarks", [*synthesis.new_datasets, *synthesis.new_benchmarks]
        )
    )
    lines.extend(_findings_section("Contradictory or Competing Findings", synthesis.contradictions))
    lines.extend(_list_section("Changes From Previous Weeks", synthesis.changes_from_history))
    lines.extend(_findings_section("Open Research Problems", synthesis.common_limitations))
    return lines


def _findings_section(heading: str, findings: list[SupportedFinding]) -> list[str]:
    lines = ["", f"## {heading}", ""]
    if not findings:
        lines.append("Nothing recorded for this period.")
        return lines
    lines.extend(
        f"- {inline(finding.text)} ({', '.join(finding.supporting_paper_ids)})"
        for finding in findings
    )
    return lines


def _list_section(heading: str, values: list[str]) -> list[str]:
    items = [f"- {inline(value)}" for value in values if value.strip()]
    return ["", f"## {heading}", "", *(items or ["Nothing recorded for this period."])]


def _papers(inputs: ReportInputs) -> list[str]:
    lines = ["", "## Important New Papers", ""]
    for analysis in inputs.analyses:
        paper = inputs.papers.get(analysis.paper_id)
        title = inline(paper.title) if paper else analysis.paper_id
        depth = " _(abstract-only)_" if analysis.abstract_only else ""
        lines.extend(
            [
                f"### {title}{depth}",
                "",
                f"- **Paper:** `{analysis.paper_id}`{_link(paper)}",
                f"- **Contribution:** {inline(analysis.main_contribution)}",
            ]
        )
        if analysis.main_results:
            lines.append(f"- **Results:** {inline('; '.join(analysis.main_results))}")
        if analysis.limitations:
            lines.append(f"- **Limitations:** {inline('; '.join(analysis.limitations))}")
        lines.append(f"- **Relevance:** {inline(analysis.topic_relevance)}")
        lines.append("")
    return lines


def _reading_order(inputs: ReportInputs) -> list[str]:
    tiers: dict[str, list[str]] = {"Essential": [], "Useful": [], "Peripheral": []}
    actions = {result.paper_id: result.action for result in inputs.classifications}
    for analysis in inputs.analyses:
        action = actions.get(analysis.paper_id)
        tier = (
            "Essential" if action in _ESSENTIAL else "Useful" if action in _USEFUL else "Peripheral"
        )
        paper = inputs.papers.get(analysis.paper_id)
        tiers[tier].append(f"- {inline(paper.title) if paper else analysis.paper_id}")
    lines = ["", "## Recommended Reading Order"]
    for tier, entries in tiers.items():
        lines.extend(["", f"### {tier}", ""])
        lines.extend(entries or ["None this period."])
    return lines


def _ideation(inputs: ReportInputs) -> list[str]:
    lines = ["", "## Research Gaps", ""]
    if inputs.gaps:
        for gap in inputs.gaps:
            confidence = "unstated" if gap.confidence is None else f"{gap.confidence:.2f}"
            lines.append(
                f"- **{inline(gap.title)}** (confidence {confidence}; "
                f"{', '.join(gap.supporting_paper_ids)}): {inline(gap.description)}"
            )
    else:
        lines.append("No gap was supported by a paper in this period.")
    lines.extend(["", "## Potential Research Ideas", ""])
    if inputs.ideas:
        for idea in inputs.ideas:
            lines.extend(
                [
                    f"### {inline(idea.title)}",
                    "",
                    f"- **Addresses gap:** {inline(idea.identified_gap)}",
                    f"- **Supported by:** {', '.join(idea.supporting_paper_ids)}",
                    f"- **Hypothesis:** {inline(idea.hypothesis)}",
                    f"- **Proposed direction:** {inline(idea.proposed_direction)}",
                    f"- **Evaluation plan:** {inline(idea.evaluation_plan)}",
                ]
            )
            if idea.risks:
                lines.append(f"- **Risks:** {inline('; '.join(idea.risks))}")
            lines.append("")
    else:
        lines.append("No idea survived reference validation this period.")
    return lines


def _sources(inputs: ReportInputs) -> list[str]:
    lines = ["", "## Sources", ""]
    entries: list[str] = []
    for paper_id in sorted(inputs.papers):
        paper = inputs.papers[paper_id]
        links = ", ".join(
            reference.url or reference.pdf_url or reference.source
            for reference in paper.sources
            if reference.url or reference.pdf_url or reference.source
        )
        entries.append(f"- `{paper_id}` {inline(paper.title)}{_link(paper)} — {links}")
    lines.extend(entries or ["No paper source was recorded for this period."])
    return lines


def _provenance(inputs: ReportInputs) -> list[str]:
    run, topic = inputs.run, inputs.topic
    summary = run.summary
    discovery = [
        name
        for name, enabled in (
            ("openalex", topic.discovery.openalex),
            ("semantic_scholar", topic.discovery.semantic_scholar),
            ("arxiv", topic.discovery.arxiv),
        )
        if enabled
    ]
    models = sorted({analysis.model_name for analysis in inputs.analyses})
    lines = [
        "",
        "## Run Provenance",
        "",
        f"- **Run:** `{run.id}`, status `{run.status}`",
        f"- **Started:** {run.started_at.isoformat()}",
        f"- **Lookback:** {topic.lookback_days} day(s)",
        f"- **Sources enabled:** {', '.join(discovery) or 'none'}",
        f"- **Classifier:** active {run.active_classifier}"
        + (f", shadow {run.shadow_classifier}" if run.shadow_classifier else ", no shadow"),
        f"- **Limits:** {topic.limits.max_candidates} candidates, "
        f"{topic.limits.max_classified} classified, {topic.limits.max_downloads} downloads, "
        f"{topic.limits.max_deep_reads} deep reads",
        f"- **Analysis models:** {', '.join(models) or 'none'}",
    ]
    if summary is not None:
        lines.append(
            f"- **Counts:** {summary.candidates_discovered} discovered, "
            f"{summary.candidates_deduplicated} after deduplication, "
            f"{summary.papers_classified} classified, {summary.papers_selected} selected, "
            f"{summary.deep_reads} deep read(s)"
        )
    if inputs.errors:
        lines.extend(["", "### Recorded Errors", ""])
        lines.extend(
            f"- `{error.category}` in `{error.node}`: {inline(error.message)}"
            for error in inputs.errors
        )
    return lines


def _degraded(inputs: ReportInputs) -> bool:
    return bool(inputs.errors) or inputs.run.status in ("degraded", "failed")


def _link(paper: PaperCandidate | None) -> str:
    if paper is None:
        return ""
    if paper.doi:
        return f" <{_DOI_BASE}{paper.doi}>"
    if paper.arxiv_id:
        return f" <{_ARXIV_BASE}{paper.arxiv_id}>"
    return ""
