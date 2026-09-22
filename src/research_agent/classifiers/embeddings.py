"""Optional local embeddings for Classifier A, over the OpenAI-compatible `/embeddings` shape."""

import math
from typing import Any

import httpx

from research_agent.classifiers.base import ClassifierError
from research_agent.config import ModelEndpointSettings
from research_agent.discovery.http import RateLimiter, SourceRequestError, request_json


def cosine(left: list[float], right: list[float]) -> float:
    """Cosine similarity clamped to 0-1; unusable vectors score zero rather than raising."""
    if len(left) != len(right) or not left:
        return 0.0
    norm = math.sqrt(sum(value * value for value in left)) * math.sqrt(
        sum(value * value for value in right)
    )
    if norm == 0:
        return 0.0
    similarity = sum(a * b for a, b in zip(left, right, strict=True)) / norm
    return max(0.0, min(1.0, similarity))


class EmbeddingClient:
    """Embed a batch of texts with the configured local runtime."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        model: str,
        settings: ModelEndpointSettings | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._settings = settings or ModelEndpointSettings()
        self._limiter = RateLimiter(self._settings.requests_per_second)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed every text in one request; the endpoint keeps the input order."""
        if not texts:
            return []
        headers = {"content-type": "application/json"}
        if self._settings.api_key:
            headers["authorization"] = f"Bearer {self._settings.api_key}"
        try:
            payload = await request_json(
                self._client,
                f"{self._settings.base_url.rstrip('/')}/embeddings",
                method="POST",
                json_body={"model": self._model, "input": texts},
                headers=headers,
                limiter=self._limiter,
                retries=0,
                error_category="MODEL_API_ERROR",
                transient_category="MODEL_TIMEOUT",
            )
        except SourceRequestError as error:
            # The message names the URL and status only; credentials never reach it.
            raise ClassifierError(f"embedding request failed: {error}", error.category) from error
        return _vectors(payload, len(texts))


def _vectors(payload: dict[str, Any], expected: int) -> list[list[float]]:
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != expected:
        raise ClassifierError("embedding endpoint returned an unexpected number of vectors")
    vectors: list[list[float]] = []
    for entry in data:
        vector = entry.get("embedding") if isinstance(entry, dict) else None
        if not isinstance(vector, list) or not all(
            isinstance(value, int | float) for value in vector
        ):
            raise ClassifierError("embedding endpoint returned a malformed vector")
        vectors.append([float(value) for value in vector])
    return vectors
