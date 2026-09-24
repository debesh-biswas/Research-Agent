import asyncio
import json

import httpx
import pytest

from research_agent.classifiers.base import ClassifierError
from research_agent.classifiers.embeddings import EmbeddingClient, cosine
from research_agent.config import ModelEndpointSettings
from tests.unit.conftest import mock_client


def vectors(*values: list[float]) -> dict[str, object]:
    return {"data": [{"embedding": vector} for vector in values]}


def client(handler: object, model: str = "nomic-embed-text") -> EmbeddingClient:
    return EmbeddingClient(
        mock_client(handler),  # type: ignore[arg-type]
        model,
        ModelEndpointSettings(base_url="http://localhost:11434/v1"),
    )


def test_a_batch_becomes_one_request_in_input_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        body = json.loads(request.content)
        assert body == {"model": "nomic-embed-text", "input": ["a", "b"]}
        return httpx.Response(200, json=vectors([1.0, 0.0], [0.0, 1.0]))

    assert asyncio.run(client(handler).embed(["a", "b"])) == [[1.0, 0.0], [0.0, 1.0]]


def test_an_empty_batch_never_leaves_the_process() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    assert asyncio.run(client(handler).embed([])) == []


def test_a_transport_failure_becomes_a_classifier_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(ClassifierError) as error:
        asyncio.run(client(handler).embed(["a"]))

    assert error.value.category == "MODEL_TIMEOUT"


def test_a_short_response_is_rejected_rather_than_misaligned() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=vectors([1.0]))

    with pytest.raises(ClassifierError, match="unexpected number"):
        asyncio.run(client(handler).embed(["a", "b"]))


def test_a_malformed_vector_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": ["not a number"]}]})

    with pytest.raises(ClassifierError, match="malformed"):
        asyncio.run(client(handler).embed(["a"]))


def test_an_api_key_is_sent_but_never_echoed_in_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-value"
        return httpx.Response(404)

    embedder = EmbeddingClient(
        mock_client(handler),
        "nomic-embed-text",
        ModelEndpointSettings(base_url="http://localhost:11434/v1", api_key="secret-value"),
    )

    with pytest.raises(ClassifierError) as error:
        asyncio.run(embedder.embed(["a"]))

    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ([1.0, 0.0], [1.0, 0.0], 1.0),
        ([1.0, 0.0], [0.0, 1.0], 0.0),
        ([1.0, 0.0], [-1.0, 0.0], 0.0),
        ([0.0, 0.0], [1.0, 0.0], 0.0),
        ([1.0], [1.0, 0.0], 0.0),
        ([], [], 0.0),
    ],
)
def test_cosine_is_clamped_and_shape_safe(
    left: list[float], right: list[float], expected: float
) -> None:
    assert cosine(left, right) == pytest.approx(expected)
