import asyncio
import json

import httpx
import pytest
from conftest import candidate, mock_client

from research_agent.classifiers.base import ClassifierError
from research_agent.classifiers.classifier_b import ClassifierB
from research_agent.classifiers.prompts import PROMPT_VERSION
from research_agent.config import ApplicationSettings, ClassifierBSettings, TopicSettings
from research_agent.domain.analysis import ClassificationResult
from research_agent.models.router import build_router

VERDICT = {
    "relevance": "high",
    "relevance_score": 0.9,
    "paper_type": "method",
    "action": "deep_read",
    "confidence": 0.8,
    "reason_short": "central to the topic",
}


def topic() -> TopicSettings:
    return TopicSettings.model_validate(
        {
            "id": "spatial_intelligence",
            "name": "Spatial Intelligence",
            "keywords": ["embodied navigation"],
        }
    )


def completion(content: str) -> dict[str, object]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


def classifier(handler: object, settings: ClassifierBSettings | None = None) -> ClassifierB:
    router = build_router(
        mock_client(handler),  # type: ignore[arg-type]
        ApplicationSettings(),
    )
    return ClassifierB(router, settings)


def replying(*contents: str) -> tuple[object, list[dict[str, object]]]:
    """A transport that answers with each content in turn, recording every request body."""
    sent: list[dict[str, object]] = []
    remaining = list(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=completion(remaining.pop(0) if remaining else "{}"))

    return handler, sent


def test_a_valid_reply_becomes_a_normalized_result() -> None:
    handler, sent = replying(json.dumps(VERDICT))

    result = asyncio.run(classifier(handler).classify(candidate(), topic()))

    assert isinstance(result, ClassificationResult)
    assert (result.classifier_name, result.relevance, result.action) == (
        "classifier_b",
        "high",
        "deep_read",
    )
    assert result.latency_ms is not None
    assert len(sent) == 1


def test_malformed_output_is_repaired_once_and_then_succeeds() -> None:
    handler, sent = replying("not json at all", json.dumps(VERDICT))

    result = asyncio.run(classifier(handler).classify(candidate(), topic()))

    assert result.action == "deep_read"
    assert len(sent) == 2
    assert "not valid JSON" in str(sent[1]["messages"])


def test_a_second_malformed_reply_is_not_retried_again() -> None:
    handler, sent = replying("nope", "still nope")

    with pytest.raises(ClassifierError) as error:
        asyncio.run(classifier(handler).classify(candidate(), topic()))

    assert error.value.category == "INVALID_CLASSIFIER_OUTPUT"
    assert len(sent) == 2


def test_a_provider_failure_becomes_a_classifier_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(ClassifierError) as error:
        asyncio.run(classifier(handler).classify(candidate(), topic()))

    assert error.value.category == "MODEL_TIMEOUT"


def test_one_failing_paper_does_not_lose_the_rest_of_a_batch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if "Tax Policy" in str(body["messages"]):
            return httpx.Response(500)
        return httpx.Response(200, json=completion(json.dumps(VERDICT)))

    papers = [candidate(), candidate(title="Tax Policy", doi="10.1/x"), candidate(doi="10.1/y")]

    results = asyncio.run(classifier(handler).classify_many(papers, topic()))

    assert len(results) == 2


def test_a_long_abstract_is_truncated_in_the_prompt() -> None:
    handler, sent = replying(json.dumps(VERDICT))
    paper = candidate(abstract="word " * 2000)

    asyncio.run(
        classifier(handler, ClassifierBSettings(max_abstract_chars=50)).classify(paper, topic())
    )

    prompt = str(sent[0]["messages"])
    assert "[abstract truncated]" in prompt
    assert len(prompt) < 2000


def test_a_missing_abstract_is_stated_rather_than_omitted() -> None:
    handler, sent = replying(json.dumps(VERDICT))

    asyncio.run(classifier(handler).classify(candidate(abstract=None), topic()))

    assert "none available" in str(sent[0]["messages"])


def test_provenance_names_the_prompt_and_the_model() -> None:
    handler, _ = replying(json.dumps(VERDICT))

    ((_, provenance),) = asyncio.run(classifier(handler).explain_many([candidate()], topic()))

    assert provenance["version"] == PROMPT_VERSION
    assert provenance["model_provider"] == "local"
    assert provenance["repaired"] is False


def test_provenance_records_that_a_repair_was_needed() -> None:
    handler, _ = replying("nope", json.dumps(VERDICT))

    ((_, provenance),) = asyncio.run(classifier(handler).explain_many([candidate()], topic()))

    assert provenance["repaired"] is True


def test_an_empty_batch_makes_no_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    assert asyncio.run(classifier(handler).explain_many([], topic())) == []
