"""Run lifecycle and error records."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from research_agent.config import StrictModel

RunStatus = Literal["running", "completed", "degraded", "failed"]

ErrorCategory = Literal[
    "DISCOVERY_ERROR",
    "RATE_LIMIT",
    "NETWORK_ERROR",
    "CLASSIFIER_ERROR",
    "INVALID_CLASSIFIER_OUTPUT",
    "PDF_DOWNLOAD_ERROR",
    "PDF_PARSE_ERROR",
    "MODEL_API_ERROR",
    "MODEL_TIMEOUT",
    "STORAGE_ERROR",
    "REPORT_ERROR",
]


class RunSummary(StrictModel):
    """Per-run counters and model choices, persisted so a run can be reconstructed."""

    candidates_discovered: int = Field(default=0, ge=0)
    candidates_deduplicated: int = Field(default=0, ge=0)
    papers_classified: int = Field(default=0, ge=0)
    papers_selected: int = Field(default=0, ge=0)
    downloads_succeeded: int = Field(default=0, ge=0)
    parse_failures: int = Field(default=0, ge=0)
    deep_reads: int = Field(default=0, ge=0)
    models_used: list[str] = Field(default_factory=list)
    errors: int = Field(default=0, ge=0)


class RunRecord(StrictModel):
    """One weekly run of the workflow for a single topic."""

    id: str = Field(min_length=1)
    topic_id: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime | None = None
    status: RunStatus = "running"
    active_classifier: Literal["A", "B"] = "A"
    shadow_classifier: Literal["A", "B"] | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    summary: RunSummary | None = None


class ErrorRecord(StrictModel):
    """A categorized failure, recorded so partial progress stays observable."""

    run_id: str = Field(min_length=1)
    node: str = Field(min_length=1)
    category: ErrorCategory
    message: str
    recoverable: bool = True
    paper_id: str | None = None
    occurred_at: datetime | None = None
