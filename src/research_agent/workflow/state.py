"""The graph's validated state.

State carries identifiers, paths and counts only. Document text and PDF bytes stay on disk behind
the artifact store, which is what keeps a run's state small enough to checkpoint and log.
"""

from datetime import date

from pydantic import Field, model_validator

from research_agent.config import StrictModel
from research_agent.domain.analysis import ClassificationResult
from research_agent.domain.papers import PaperCandidate
from research_agent.domain.runs import ErrorRecord, RunStatus

_MAX_PATH_CHARS = 1024


class ResearchState(StrictModel):
    """One run's progress through the graph."""

    topic_id: str = Field(min_length=1)
    period_start: date
    period_end: date
    run_id: str | None = None

    queries: list[str] = Field(default_factory=list)
    broadened: bool = False
    """True once the single automatic broadening pass has been used; it is never used twice."""

    candidates: list[PaperCandidate] = Field(default_factory=list)
    classifications: list[ClassificationResult] = Field(default_factory=list)
    selected_ids: list[str] = Field(default_factory=list)
    pdf_paths: dict[str, str] = Field(default_factory=dict)
    parsed_paths: dict[str, str] = Field(default_factory=dict)
    analyzed_ids: list[str] = Field(default_factory=list)
    abstract_only_ids: list[str] = Field(default_factory=list)
    gap_count: int = Field(default=0, ge=0)
    idea_count: int = Field(default=0, ge=0)
    synthesized: bool = False
    report_path: str | None = None
    empty_week: bool = False

    counts: dict[str, int] = Field(default_factory=dict)
    errors: list[ErrorRecord] = Field(default_factory=list)
    status: RunStatus = "running"

    @model_validator(mode="after")
    def keep_artifacts_out_of_state(self) -> "ResearchState":
        """Reject anything that is a document rather than a reference to one.

        Without this the graph would quietly start carrying whole papers between nodes, which the
        TRD forbids and which would make checkpoints unusable.
        """
        for label, mapping in (("pdf_paths", self.pdf_paths), ("parsed_paths", self.parsed_paths)):
            for paper_id, value in mapping.items():
                if "\n" in value or len(value) > _MAX_PATH_CHARS:
                    raise ValueError(f"{label}[{paper_id}] must be a path, not document content")
        return self
