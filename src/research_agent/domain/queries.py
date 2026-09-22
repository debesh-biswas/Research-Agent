"""The search plan a topic resolves to before any source is queried (TRD section 17)."""

from datetime import datetime

from pydantic import Field

from research_agent.config import StrictModel


class ExpandedQueries(StrictModel):
    """The only thing a model is allowed to supply; provenance is filled in by the planner."""

    queries: list[str] = Field(default_factory=list)


class QueryPlan(StrictModel):
    """A bounded, reproducible set of searches plus the provenance needed to audit it."""

    topic_id: str = Field(min_length=1)
    queries: list[str] = Field(min_length=1)
    base_query: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    model_provider: str | None = None
    model_name: str | None = None
    fell_back: bool = False
    created_at: datetime
