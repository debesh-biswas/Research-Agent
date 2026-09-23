import httpx
import pytest

from research_agent.classifiers.base import PaperClassifier
from research_agent.classifiers.classifier_a import ClassifierA
from research_agent.classifiers.classifier_b import ClassifierB
from research_agent.classifiers.factory import build_classifier
from research_agent.config import ApplicationSettings, ClassifierASettings


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))


@pytest.mark.parametrize(
    ("name", "expected"),
    [("A", ClassifierA), ("a", ClassifierA), ("B", ClassifierB), ("b", ClassifierB)],
)
def test_configuration_alone_selects_the_implementation(name: str, expected: type) -> None:
    classifier = build_classifier(name, client(), ApplicationSettings())

    assert isinstance(classifier, expected)


def test_both_classifiers_satisfy_the_protocol() -> None:
    settings = ApplicationSettings()

    for name in ("A", "B"):
        classifier: PaperClassifier = build_classifier(name, client(), settings)
        assert classifier.name.startswith("classifier_")


def test_an_unsupported_classifier_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported classifier: C"):
        build_classifier("C", client(), ApplicationSettings())


def test_classifier_a_gets_an_embedder_only_when_one_is_configured() -> None:
    without = build_classifier("A", client(), ApplicationSettings())
    with_embeddings = build_classifier(
        "A",
        client(),
        ApplicationSettings(classifier_a=ClassifierASettings(embedding_model="nomic-embed-text")),
    )

    assert isinstance(without, ClassifierA) and without._embedder is None
    assert isinstance(with_embeddings, ClassifierA) and with_embeddings._embedder is not None
