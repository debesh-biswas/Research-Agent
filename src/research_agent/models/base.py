"""The provider-neutral inference contract every caller depends on."""

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from research_agent.config import StrictModel
from research_agent.domain.runs import ErrorCategory

Capability = Literal[
    "cheap_text",
    "classification",
    "deep_reasoning",
    "synthesis",
    "ideation",
    "report_writing",
]

# TRD section 26. Strong capabilities resolve to the configured strong provider, falling back to
# local inference; the mapping is fixed by the specification, so it is code rather than settings.
STRONG_CAPABILITIES: frozenset[Capability] = frozenset(
    {"deep_reasoning", "synthesis", "ideation", "report_writing"}
)


class ModelMessage(StrictModel):
    """One chat turn, in the shape every OpenAI-compatible endpoint accepts."""

    role: Literal["system", "user", "assistant"]
    content: str


class ModelResult(StrictModel):
    """A completion plus the provenance a run summary and audit trail need."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    text: str
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    fell_back: bool = False
    parsed: BaseModel | None = None
    """The validated structured response when a schema was requested; ``text`` keeps the raw."""


class ModelProviderError(Exception):
    """An inference call failed; the category feeds the run error taxonomy."""

    def __init__(self, message: str, category: ErrorCategory = "MODEL_API_ERROR") -> None:
        super().__init__(message)
        self.category: ErrorCategory = category


class ModelProvider(Protocol):
    """One inference backend, independent of its vendor."""

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def generate(
        self,
        task: str,
        messages: list[ModelMessage],
        response_schema: type[BaseModel] | None = None,
    ) -> ModelResult: ...


class ModelValidationError(ModelProviderError):
    """Structured output failed its schema; deterministic, so it is never retried by the router."""
