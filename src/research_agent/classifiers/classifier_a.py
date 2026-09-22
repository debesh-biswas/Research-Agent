"""Classifier A: the lightweight, low-latency triage path (PRD 7.1, TRD section 11).

It is deterministic by default — lexical scoring only, no network, no model — and blends in local
embedding similarity when one is configured. Nothing here is trained or fine-tuned. If a different
lightweight implementation is adopted later, this module is the only one that should change.
"""

import logging
import time
from typing import Literal

from research_agent.classifiers.base import ClassifierError
from research_agent.classifiers.embeddings import EmbeddingClient, cosine
from research_agent.classifiers.lexical import CUE_VERSION, detect_paper_type, lexical_score
from research_agent.config import ClassifierASettings, TopicSettings
from research_agent.discovery.normalize import canonical_id
from research_agent.domain.analysis import ClassificationResult
from research_agent.domain.papers import PaperCandidate

_LOGGER = logging.getLogger(__name__)

# ponytail: confidence is the distance to the nearest decision boundary, saturating at this width.
# A calibrated probability needs labelled data, which v1 deliberately does not collect.
_CONFIDENCE_SPAN = 0.25

Relevance = Literal["high", "medium", "low"]
Action = Literal["ignore", "summarize", "deep_read"]
Provenance = dict[str, object]


class ClassifierA:
    """Score papers against a topic and turn the score into a relevance, action, and confidence."""

    name = "classifier_a"

    def __init__(
        self,
        settings: ClassifierASettings | None = None,
        embedder: EmbeddingClient | None = None,
    ) -> None:
        self._settings = settings or ClassifierASettings()
        self._embedder = embedder

    async def classify(self, paper: PaperCandidate, topic: TopicSettings) -> ClassificationResult:
        results = await self.classify_many([paper], topic)
        return results[0]

    async def classify_many(
        self, papers: list[PaperCandidate], topic: TopicSettings
    ) -> list[ClassificationResult]:
        return [result for result, _ in await self.explain_many(papers, topic)]

    async def explain_many(
        self, papers: list[PaperCandidate], topic: TopicSettings
    ) -> list[tuple[ClassificationResult, Provenance]]:
        """Classify a batch, returning each verdict with the audit payload that produced it.

        Embeddings, when enabled, are requested once for the whole batch rather than per paper.
        """
        started = time.monotonic()
        similarities = await self._similarities(papers, topic)
        latency_ms = int((time.monotonic() - started) * 1000)
        return [
            self._verdict(paper, topic, similarity, latency_ms)
            for paper, similarity in zip(papers, similarities, strict=True)
        ]

    async def _similarities(
        self, papers: list[PaperCandidate], topic: TopicSettings
    ) -> list[float | None]:
        """Embedding similarity per paper, or None for every paper when it is unavailable."""
        if self._embedder is None or not papers:
            return [None] * len(papers)
        topic_text = " ".join([topic.name, *topic.keywords])
        texts = [f"{paper.title}\n{paper.abstract or ''}" for paper in papers]
        try:
            vectors = await self._embedder.embed([topic_text, *texts])
        except ClassifierError as error:
            _LOGGER.warning(
                "embedding similarity unavailable; scoring lexically",
                extra={
                    "topic_id": topic.id,
                    "node_name": "classify",
                    "error_type": error.category,
                    "status": "degraded",
                },
            )
            return [None] * len(papers)
        return [cosine(vectors[0], vector) for vector in vectors[1:]]

    def _verdict(
        self,
        paper: PaperCandidate,
        topic: TopicSettings,
        similarity: float | None,
        latency_ms: int,
    ) -> tuple[ClassificationResult, Provenance]:
        lexical, matched = lexical_score(paper, topic)
        weight = 0.0 if similarity is None else self._settings.embedding_weight
        score = (1 - weight) * lexical + weight * (similarity or 0.0)

        relevance, action = self._decide(score)
        result = ClassificationResult(
            paper_id=paper.canonical_id or canonical_id(paper),
            classifier_name=self.name,
            relevance=relevance,
            relevance_score=round(score, 4),
            paper_type=detect_paper_type(paper),
            action=action,
            confidence=self._confidence(score),
            reason_short=f"matched {', '.join(matched)}" if matched else "no topic terms matched",
            latency_ms=latency_ms,
        )
        provenance: Provenance = {
            "version": CUE_VERSION,
            "lexical_score": round(lexical, 4),
            "embedding_score": None if similarity is None else round(similarity, 4),
            "embedding_weight": weight,
            "matched_terms": matched,
        }
        return result, provenance

    def _decide(self, score: float) -> tuple[Relevance, Action]:
        if score >= self._settings.deep_read_at:
            return "high", "deep_read"
        if score >= self._settings.summarize_at:
            return "medium", "summarize"
        return "low", "ignore"

    def _confidence(self, score: float) -> float:
        margin = min(
            abs(score - self._settings.summarize_at), abs(score - self._settings.deep_read_at)
        )
        return round(min(1.0, margin / _CONFIDENCE_SPAN), 4)
