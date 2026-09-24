"""What a run decided to read, and why it decided it (TRD sections 11 and 20)."""

from typing import Literal

from pydantic import Field

from research_agent.config import StrictModel

SelectionReason = Literal[
    "selected_deep_read",
    "selected_summarize",
    "action_ignore",
    "below_threshold",
    "already_analyzed",
    "limit_reached",
]
"""Why one paper was kept or dropped. A value, not prose, so downstream code can match on it."""


class SelectionDecision(StrictModel):
    """One classified paper's outcome, recorded whether it was kept or not."""

    paper_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    selected: bool
    action: Literal["ignore", "summarize", "deep_read"]
    reason: SelectionReason


class SelectionPlan(StrictModel):
    """Every decision of one selection pass, in rank order."""

    decisions: list[SelectionDecision] = Field(default_factory=list)

    @property
    def selected_ids(self) -> list[str]:
        return [decision.paper_id for decision in self.decisions if decision.selected]

    @property
    def deep_reads(self) -> list[str]:
        return [
            decision.paper_id
            for decision in self.decisions
            if decision.reason == "selected_deep_read"
        ]

    @property
    def summaries(self) -> list[str]:
        return [
            decision.paper_id
            for decision in self.decisions
            if decision.reason == "selected_summarize"
        ]
