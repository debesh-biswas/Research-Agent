"""Schemas for classifier and model output (TRD sections 10 and 27-31)."""

from typing import Literal

from pydantic import Field

from research_agent.config import StrictModel


class ClassificationResult(StrictModel):
    """Normalized triage verdict returned by either classifier."""

    paper_id: str = Field(min_length=1)
    classifier_name: str = Field(min_length=1)
    relevance: Literal["high", "medium", "low"]
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    paper_type: Literal["method", "dataset", "benchmark", "survey", "application", "other"]
    action: Literal["ignore", "summarize", "deep_read"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason_short: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)


class Claim(StrictModel):
    """A claim with best-effort provenance back into the parsed paper."""

    text: str = Field(min_length=1)
    source_section: str | None = None
    page: int | None = Field(default=None, ge=1)
    evidence_excerpt: str | None = None


class PaperAnalysis(StrictModel):
    """Structured deep read of one paper."""

    paper_id: str = Field(min_length=1)
    research_problem: str
    main_contribution: str
    method: str
    datasets: list[str] = Field(default_factory=list)
    benchmarks: list[str] = Field(default_factory=list)
    experimental_setup: str | None = None
    main_results: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    key_claims: list[Claim] = Field(default_factory=list)
    related_work: list[str] = Field(default_factory=list)
    topic_relevance: str
    model_provider: str
    model_name: str


class WeeklySynthesis(StrictModel):
    """Cross-paper picture of one reporting period."""

    major_developments: list[str] = Field(default_factory=list)
    emerging_directions: list[str] = Field(default_factory=list)
    methods_gaining_attention: list[str] = Field(default_factory=list)
    new_datasets: list[str] = Field(default_factory=list)
    new_benchmarks: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    changes_from_history: list[str] = Field(default_factory=list)


class ResearchGap(StrictModel):
    """An unaddressed question, linked to the papers that imply it."""

    title: str = Field(min_length=1)
    description: str
    supporting_paper_ids: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ResearchIdea(StrictModel):
    """A concrete proposal derived from a detected gap."""

    title: str = Field(min_length=1)
    hypothesis: str
    motivation: str
    supporting_paper_ids: list[str] = Field(default_factory=list)
    identified_gap: str
    proposed_direction: str
    evaluation_plan: str
    risks: list[str] = Field(default_factory=list)
