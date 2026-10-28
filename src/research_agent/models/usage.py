"""Count what each run asks of the models: calls, tokens and time, per provider and model."""

from research_agent.domain.runs import ModelUsage
from research_agent.models.base import ModelResult


class UsageMeter:
    """Fed by the router with every reply, including ones that later fail validation."""

    def __init__(self) -> None:
        self._totals: dict[tuple[str, str], ModelUsage] = {}

    def record(self, result: ModelResult, *, fell_back: bool = False) -> None:
        key = (result.provider, result.model)
        seen = self._totals.get(key) or ModelUsage(provider=result.provider, model=result.model)
        self._totals[key] = seen.model_copy(
            update={
                "calls": seen.calls + 1,
                "prompt_tokens": seen.prompt_tokens + (result.prompt_tokens or 0),
                "completion_tokens": seen.completion_tokens + (result.completion_tokens or 0),
                "latency_ms": seen.latency_ms + result.latency_ms,
                "fallbacks": seen.fallbacks + int(fell_back),
            }
        )

    def totals(self) -> list[ModelUsage]:
        return [self._totals[key] for key in sorted(self._totals)]
