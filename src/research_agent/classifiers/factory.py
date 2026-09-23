"""Classifier factory (TRD section 13): switching A and B is configuration, never code."""

import httpx

from research_agent.classifiers.base import PaperClassifier
from research_agent.classifiers.classifier_a import ClassifierA
from research_agent.classifiers.classifier_b import ClassifierB
from research_agent.classifiers.embeddings import EmbeddingClient
from research_agent.config import ApplicationSettings
from research_agent.models.router import build_router


def build_classifier(
    name: str, client: httpx.AsyncClient, settings: ApplicationSettings
) -> PaperClassifier:
    """Build the named classifier with the dependencies its implementation needs."""
    match name.upper():
        case "A":
            return ClassifierA(settings.classifier_a, _embedder(client, settings))
        case "B":
            return ClassifierB(
                build_router(client, settings),
                settings.classifier_b,
                settings.concurrency.analysis,
            )
        case _:
            raise ValueError(f"unsupported classifier: {name}")


def _embedder(client: httpx.AsyncClient, settings: ApplicationSettings) -> EmbeddingClient | None:
    """Only build an embedding client when one is configured; otherwise scoring stays lexical."""
    model = settings.classifier_a.embedding_model
    if model is None:
        return None
    return EmbeddingClient(client, model, settings.models.local)
