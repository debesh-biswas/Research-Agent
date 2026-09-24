import asyncio

import httpx
import pytest

from research_agent.classifiers.base import ClassifierError
from research_agent.classifiers.classifier_a import ClassifierA
from research_agent.classifiers.embeddings import EmbeddingClient
from research_agent.config import ClassifierASettings, ModelEndpointSettings, TopicSettings
from research_agent.discovery.normalize import canonical_id
from research_agent.domain.analysis import ClassificationResult
from tests.unit.conftest import candidate, mock_client

RELEVANT = "Spatial Intelligence for Embodied Navigation"


def topic() -> TopicSettings:
    return TopicSettings.model_validate(
        {
            "id": "spatial_intelligence",
            "name": "Spatial Intelligence",
            "keywords": ["embodied navigation"],
        }
    )


def classify(
    classifier: ClassifierA, title: str, abstract: str | None = None
) -> ClassificationResult:
    return asyncio.run(classifier.classify(candidate(title=title, abstract=abstract), topic()))


def test_a_strongly_matching_paper_is_routed_to_a_deep_read() -> None:
    result = classify(ClassifierA(), RELEVANT, "We study spatial intelligence.")

    assert (result.relevance, result.action) == ("high", "deep_read")
    assert result.classifier_name == "classifier_a"
    assert result.relevance_score is not None and result.relevance_score >= 0.6


def test_an_unrelated_paper_is_ignored_with_a_stated_reason() -> None:
    result = classify(ClassifierA(), "Tax Policy in Northern Europe", "A fiscal study.")

    assert (result.relevance, result.action) == ("low", "ignore")
    assert result.reason_short == "no topic terms matched"


def test_a_partial_match_is_summarized_rather_than_read_deeply() -> None:
    result = classify(ClassifierA(), "Embodied Navigation in Warehouses")

    assert (result.relevance, result.action) == ("medium", "summarize")


@pytest.mark.parametrize(
    ("score", "expected"),
    [(0.9, ("high", "deep_read")), (0.45, ("medium", "summarize")), (0.1, ("low", "ignore"))],
)
def test_thresholds_are_configurable(score: float, expected: tuple[str, str]) -> None:
    # Thresholds that bracket the parametrized score exactly, so the mapping alone is under test.
    classifier = ClassifierA(ClassifierASettings(summarize_at=0.2, deep_read_at=0.8))

    assert classifier._decide(score) == expected


def test_confidence_falls_to_zero_at_a_decision_boundary() -> None:
    classifier = ClassifierA(ClassifierASettings(summarize_at=0.3, deep_read_at=0.6))

    assert classifier._confidence(0.6) == 0.0
    assert classifier._confidence(0.0) == 1.0
    assert 0.0 <= classifier._confidence(0.5) <= 1.0


def test_a_verdict_carries_latency_and_a_stable_paper_id() -> None:
    result = classify(ClassifierA(), RELEVANT)

    assert result.latency_ms is not None and result.latency_ms >= 0
    assert result.paper_id == canonical_id(candidate(title=RELEVANT))


def test_an_assigned_canonical_id_is_preferred_over_a_recomputed_one() -> None:
    paper = candidate(title=RELEVANT, canonical_id="doi_10_1_x")

    assert asyncio.run(ClassifierA().classify(paper, topic())).paper_id == "doi_10_1_x"


def test_single_and_batch_classification_agree() -> None:
    classifier = ClassifierA()
    papers = [candidate(title=RELEVANT), candidate(title="Tax Policy", doi="10.1/x")]

    batch = asyncio.run(classifier.classify_many(papers, topic()))
    single = [asyncio.run(classifier.classify(paper, topic())) for paper in papers]

    assert [(r.relevance, r.action, r.relevance_score) for r in batch] == [
        (r.relevance, r.action, r.relevance_score) for r in single
    ]


def test_an_empty_batch_returns_nothing() -> None:
    assert asyncio.run(ClassifierA().classify_many([], topic())) == []


def embedder(handler: object) -> EmbeddingClient:
    return EmbeddingClient(
        mock_client(handler),  # type: ignore[arg-type]
        "nomic-embed-text",
        ModelEndpointSettings(base_url="http://localhost:11434/v1"),
    )


def test_embedding_similarity_lifts_a_lexically_invisible_paper() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # The topic and the paper embed identically, so cosine similarity is 1.0.
        return httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0]}] * 2})

    lexical_only = classify(ClassifierA(), "Wayfinding in Buildings")
    with_embeddings = classify(ClassifierA(embedder=embedder(handler)), "Wayfinding in Buildings")

    assert with_embeddings.relevance_score is not None
    assert lexical_only.relevance_score is not None
    assert with_embeddings.relevance_score > lexical_only.relevance_score
    assert (lexical_only.action, with_embeddings.action) == ("ignore", "summarize")


def test_an_embedding_failure_degrades_to_the_lexical_verdict() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    degraded = classify(ClassifierA(embedder=embedder(handler)), RELEVANT)
    lexical_only = classify(ClassifierA(), RELEVANT)

    assert degraded.relevance_score == lexical_only.relevance_score
    assert degraded.action == lexical_only.action


def test_provenance_records_how_a_score_was_reached() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0]}] * 2})

    explained = asyncio.run(
        ClassifierA(embedder=embedder(handler)).explain_many([candidate(title=RELEVANT)], topic())
    )

    _, provenance = explained[0]
    assert provenance["version"] == "classifier_a.v1"
    assert provenance["embedding_score"] == 1.0
    assert provenance["embedding_weight"] == 0.5
    assert "spatial intelligence" in provenance["matched_terms"]  # type: ignore[operator]


def test_provenance_marks_a_purely_lexical_verdict() -> None:
    ((_, provenance),) = asyncio.run(
        ClassifierA().explain_many([candidate(title=RELEVANT)], topic())
    )

    assert provenance["embedding_score"] is None
    assert provenance["embedding_weight"] == 0.0


def test_a_malformed_embedding_response_does_not_fail_the_batch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    with pytest.raises(ClassifierError):
        asyncio.run(embedder(handler).embed(["a"]))

    assert classify(ClassifierA(embedder=embedder(handler)), RELEVANT).action == "deep_read"
