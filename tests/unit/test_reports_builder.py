from datetime import UTC, date, datetime

from research_agent.config import TopicSettings
from research_agent.domain.analysis import (
    ClassificationResult,
    PaperAnalysis,
    ResearchGap,
    ResearchIdea,
    SupportedFinding,
    WeeklySynthesis,
)
from research_agent.domain.runs import ErrorRecord, RunRecord, RunSummary
from research_agent.reports.builder import ReportInputs, build_report
from research_agent.reports.naming import is_report, report_filename
from tests.unit.conftest import TOPIC_ID, candidate

START = date(2026, 9, 17)
END = date(2026, 9, 27)


def topic() -> TopicSettings:
    return TopicSettings.model_validate(
        {"id": TOPIC_ID, "name": "Spatial Intelligence", "keywords": ["embodied navigation"]}
    )


def run(**overrides: object) -> RunRecord:
    payload: dict[str, object] = {
        "id": "run1",
        "topic_id": TOPIC_ID,
        "started_at": datetime(2026, 9, 27, 12, tzinfo=UTC),
        "status": "completed",
        "active_classifier": "A",
        "summary": RunSummary(
            candidates_discovered=40,
            candidates_deduplicated=30,
            papers_classified=20,
            papers_selected=2,
            deep_reads=1,
        ),
    }
    payload.update(overrides)
    return RunRecord.model_validate(payload)


def analysis(paper_id: str, **overrides: object) -> PaperAnalysis:
    payload: dict[str, object] = {
        "paper_id": paper_id,
        "research_problem": "Agents cannot reason about unseen rooms.",
        "main_contribution": f"Contribution of {paper_id}.",
        "method": "A transformer over a metric map.",
        "main_results": ["+7 SPL over the baseline"],
        "limitations": ["Simulation only"],
        "topic_relevance": "Directly on topic.",
        "model_provider": "nvidia_nim",
        "model_name": "some-model",
        "prompt_version": "paper_analysis.v1",
    }
    payload.update(overrides)
    return PaperAnalysis.model_validate(payload)


def synthesis() -> WeeklySynthesis:
    return WeeklySynthesis(
        major_developments=[
            SupportedFinding(text="Metric control is benchmarked", supporting_paper_ids=["p1"])
        ],
        emerging_directions=[
            SupportedFinding(text="Active perception budgets", supporting_paper_ids=["p2"])
        ],
        contradictions=[
            SupportedFinding(text="p1 and p2 disagree", supporting_paper_ids=["p1", "p2"])
        ],
        common_limitations=[SupportedFinding(text="Simulation only", supporting_paper_ids=["p1"])],
        new_datasets=["HM3D"],
        new_benchmarks=["ObjectNav"],
        changes_from_history=["Metric control is new this period"],
        paper_ids=["p1", "p2"],
        model_provider="nvidia_nim",
        model_name="some-model",
        prompt_version="weekly_synthesis.v1",
    )


def inputs(**overrides: object) -> ReportInputs:
    papers = {
        "p1": candidate(canonical_id="p1", doi="10.1234/abcd", title="Spatial Memory for Robots"),
        "p2": candidate(
            canonical_id="p2", arxiv_id="2609.19554", title="Active Perception Budgets"
        ),
    }
    payload: dict[str, object] = {
        "topic": topic(),
        "run": run(),
        "period_start": START,
        "period_end": END,
        "papers": papers,
        "analyses": [analysis("p1"), analysis("p2")],
        "classifications": [
            ClassificationResult(
                paper_id="p1",
                classifier_name="classifier_a",
                relevance="high",
                paper_type="benchmark",
                action="deep_read",
            ),
            ClassificationResult(
                paper_id="p2",
                classifier_name="classifier_a",
                relevance="medium",
                paper_type="method",
                action="summarize",
            ),
        ],
        "synthesis": synthesis(),
        "gaps": [
            ResearchGap(
                title="No long-horizon benchmark",
                description="Benchmarks stop at 50 steps.",
                supporting_paper_ids=["p1"],
                confidence=0.6,
                model_provider="nvidia_nim",
                model_name="some-model",
                prompt_version="research_gaps.v1",
            )
        ],
        "ideas": [
            ResearchIdea(
                title="Persistent map benchmark",
                hypothesis="Longer horizons expose memory failures.",
                motivation="Scores saturate.",
                supporting_paper_ids=["p1"],
                identified_gap="No long-horizon benchmark",
                proposed_direction="Extend episodes.",
                evaluation_plan="Compare SPL across horizons.",
                risks=["Compute cost"],
                model_provider="nvidia_nim",
                model_name="some-model",
                prompt_version="research_ideas.v1",
            )
        ],
    }
    payload.update(overrides)
    return ReportInputs.model_validate(payload)


def headings(report: str) -> list[str]:
    return [line for line in report.splitlines() if line.startswith("## ")]


def test_a_full_report_has_every_required_section_in_order() -> None:
    report = build_report(inputs(), "Two papers moved the benchmark forward.")

    assert headings(report) == [
        "## Topic",
        "## Reporting Period",
        "## Executive Summary",
        "## Most Important Developments",
        "## Emerging Research Directions",
        "## Methods Gaining Attention",
        "## New Datasets / Benchmarks",
        "## Contradictory or Competing Findings",
        "## Changes From Previous Weeks",
        "## Open Research Problems",
        "## Important New Papers",
        "## Recommended Reading Order",
        "## Research Gaps",
        "## Potential Research Ideas",
        "## Sources",
        "## Run Provenance",
    ]
    assert report.startswith("# Weekly Research Intelligence Report")
    assert "Two papers moved the benchmark forward." in report
    assert "2026-09-17 to 2026-09-27" in report


def test_the_report_is_deterministic() -> None:
    assert build_report(inputs(), "Summary.") == build_report(inputs(), "Summary.")


def test_reading_order_follows_the_classifier() -> None:
    report = build_report(inputs())
    essential = report.split("### Essential")[1].split("### Useful")[0]
    useful = report.split("### Useful")[1].split("### Peripheral")[0]

    assert "Spatial Memory for Robots" in essential
    assert "Active Perception Budgets" in useful
    assert "None this period." in report.split("### Peripheral")[1]


def test_provenance_records_the_configuration_and_counts() -> None:
    report = build_report(inputs())

    assert "- **Run:** `run1`, status `completed`" in report
    assert "active A, no shadow" in report
    assert "openalex, semantic_scholar, arxiv" in report
    assert "40 discovered, 30 after deduplication" in report
    assert "- **Analysis models:** some-model" in report


def test_source_links_use_doi_and_arxiv() -> None:
    report = build_report(inputs())
    sources = report.split("## Sources")[1]

    assert "<https://doi.org/10.1234/abcd>" in sources
    assert "<https://arxiv.org/abs/2609.19554>" in sources


def test_an_empty_week_reports_the_run_without_inventing_sections() -> None:
    report = build_report(inputs(analyses=[], papers={}, synthesis=None, gaps=[], ideas=[]))

    assert "No paper met this period's selection criteria" in report
    assert "## Important New Papers" not in report
    assert "## Recommended Reading Order" not in report
    assert "## Run Provenance" in report


def test_a_missing_synthesis_degrades_one_section() -> None:
    report = build_report(inputs(synthesis=None))

    assert "No synthesis was produced for this period" in report
    assert "## Important New Papers" in report


def test_abstract_only_analyses_are_flagged() -> None:
    report = build_report(inputs(analyses=[analysis("p1", abstract_only=True), analysis("p2")]))

    assert "1 of 2 analyses are abstract-only" in report
    assert "_(abstract-only)_" in report


def test_errors_make_the_report_declare_itself_degraded() -> None:
    errors = [
        ErrorRecord(
            run_id="run1",
            node="acquire",
            category="PDF_DOWNLOAD_ERROR",
            message="no open-access PDF",
        )
    ]

    report = build_report(inputs(errors=errors, run=run(status="degraded")))

    assert "> Degraded run: 1 recorded error(s), status `degraded`." in report
    assert "- `PDF_DOWNLOAD_ERROR` in `acquire`: no open-access PDF" in report


def test_without_prose_the_summary_is_assembled() -> None:
    report = build_report(inputs())

    assert "No model-written summary was available" in report


def test_untrusted_content_cannot_inject_markup() -> None:
    report = build_report(inputs(), "```sh\nrm -rf /\n```")

    assert "```" not in report
    assert "\nrm -rf /" not in report


def test_missing_optional_findings_say_so() -> None:
    report = build_report(
        inputs(
            synthesis=synthesis().model_copy(
                update={"methods_gaining_attention": [], "changes_from_history": []}
            )
        )
    )
    methods = report.split("## Methods Gaining Attention")[1].split("## New Datasets")[0]

    assert "Nothing recorded for this period." in methods


def test_filenames_are_safe_and_sortable() -> None:
    assert report_filename(date(2026, 9, 27)) == "2026-09-27_weekly_report.md"
    assert sorted([report_filename(date(2026, 10, 4)), report_filename(END)])[-1] == (
        "2026-10-04_weekly_report.md"
    )
    assert is_report("2026-09-27_weekly_report.md")
    assert not is_report("09f88_ideation.md")
