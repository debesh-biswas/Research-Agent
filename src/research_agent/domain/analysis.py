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


class ClassifierVerdict(StrictModel):
    """The part of a verdict a model is allowed to produce; provenance is added by the adapter."""

    relevance: Literal["high", "medium", "low"]
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    paper_type: Literal["method", "dataset", "benchmark", "survey", "application", "other"]
    action: Literal["ignore", "summarize", "deep_read"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason_short: str | None = None


class Claim(StrictModel):
    """A claim with best-effort provenance back into the parsed paper."""

    text: str = Field(min_length=1)
    source_section: str | None = None
    page: int | None = Field(default=None, ge=1)
    evidence_excerpt: str | None = None


class AnalysisDraft(StrictModel):
    """The part of an analysis a model produces; the analyzer adds provenance."""

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
    prompt_version: str = Field(min_length=1)
    abstract_only: bool = False
    """True when no parsed full text was available, so a reader can tell a deep read from a skim."""


class SupportedFinding(StrictModel):
    """A cross-paper statement and the papers that support it.

    A finding with no supporting paper is not stored, so a reader can always follow a claim back
    into the corpus.
    """

    text: str = Field(min_length=1)
    supporting_paper_ids: list[str] = Field(default_factory=list)


class SynthesisDraft(StrictModel):
    """The part of a synthesis a model produces; the synthesizer adds provenance."""

    major_developments: list[SupportedFinding] = Field(default_factory=list)
    emerging_directions: list[SupportedFinding] = Field(default_factory=list)
    methods_gaining_attention: list[SupportedFinding] = Field(default_factory=list)
    contradictions: list[SupportedFinding] = Field(default_factory=list)
    common_limitations: list[SupportedFinding] = Field(default_factory=list)
    new_datasets: list[str] = Field(default_factory=list)
    new_benchmarks: list[str] = Field(default_factory=list)
    changes_from_history: list[str] = Field(default_factory=list)


class WeeklySynthesis(SynthesisDraft):
    """Cross-paper picture of one reporting period, with the provenance to reproduce it."""

    paper_ids: list[str] = Field(default_factory=list)
    """Every paper the synthesis was given, in deterministic order."""

    model_provider: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    history_periods: int = Field(default=0, ge=0)
    """How many previous syntheses were compared against; zero means no history existed."""


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
