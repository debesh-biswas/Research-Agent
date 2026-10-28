"""The reader's relevance votes as screening sees them."""

from typing import Literal

from pydantic import Field

from research_agent.config import StrictModel

Vote = Literal[-1, 1]


class FeedbackExamples(StrictModel):
    """Titles the reader marked relevant and not relevant for one topic, newest first."""

    relevant: list[str] = Field(default_factory=list)
    not_relevant: list[str] = Field(default_factory=list)
