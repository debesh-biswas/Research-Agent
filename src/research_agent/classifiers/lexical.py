"""Deterministic lexical scoring for Classifier A.

Every function here is pure: no clock, no network, no filesystem. The same paper and topic always
produce the same score, which is what makes a triage decision auditable and reproducible.
"""

from typing import Literal

from rapidfuzz import fuzz

from research_agent.config import TopicSettings
from research_agent.discovery.normalize import normalize_title
from research_agent.domain.papers import PaperCandidate

CUE_VERSION = "classifier_a.v1"
"""Bumped whenever the weights or cue table below change, so stored verdicts stay interpretable."""

PaperType = Literal["method", "dataset", "benchmark", "survey", "application", "other"]

_TOPIC_WEIGHT = 2.0
_KEYWORD_WEIGHT = 1.0
_TOKEN_WEIGHT = 0.5
_MIN_TOKEN_LENGTH = 4

# How much a term contributes when it is found, by where and how precisely it matched.
_EXACT_TITLE = 1.0
_NEAR_TITLE = 0.7
_EXACT_ABSTRACT = 0.5
_NEAR_ABSTRACT = 0.35
_NEAR_FLOOR = 90.0

# First match wins, so the order is the classification policy. `method` is last because almost
# every paper describes one; the earlier cues are the distinguishing ones.
_TYPE_CUES: tuple[tuple[PaperType, tuple[str, ...]], ...] = (
    ("survey", ("survey", "systematic review", "literature review", "taxonomy of")),
    ("benchmark", ("benchmark", "evaluation suite", "leaderboard", "we evaluate existing")),
    ("dataset", ("dataset", "corpus", "data collection", "annotated")),
    (
        "application",
        ("case study", "deployment", "in production", "clinical", "industrial", "real world"),
    ),
    ("method", ("we propose", "we introduce", "novel", "framework", "architecture", "algorithm")),
)


def topic_terms(topic: TopicSettings) -> list[tuple[str, float]]:
    """The phrases a topic is matched on: its name, weighted above each of its keywords."""
    terms: dict[str, float] = {}
    for text, weight in (
        (topic.name, _TOPIC_WEIGHT),
        *((keyword, _KEYWORD_WEIGHT) for keyword in topic.keywords),
    ):
        key = normalize_title(text)
        if key:
            terms[key] = max(terms.get(key, 0.0), weight)
    return sorted(terms.items())


def _bonus_terms(topic: TopicSettings, terms: dict[str, float]) -> list[str]:
    """Individual name tokens, which add to a score but never raise the bar for reaching it."""
    return sorted(
        {
            token
            for token in normalize_title(topic.name).split()
            if len(token) >= _MIN_TOKEN_LENGTH and token not in terms
        }
    )


def _match_factor(term: str, title: str, abstract: str) -> float:
    if term in title:
        return _EXACT_TITLE
    if title and fuzz.partial_ratio(term, title) >= _NEAR_FLOOR:
        return _NEAR_TITLE
    if term in abstract:
        return _EXACT_ABSTRACT
    if abstract and fuzz.partial_ratio(term, abstract) >= _NEAR_FLOOR:
        return _NEAR_ABSTRACT
    return 0.0


def lexical_score(paper: PaperCandidate, topic: TopicSettings) -> tuple[float, list[str]]:
    """Score a paper against a topic in 0-1, with the terms that earned the score."""
    terms = dict(topic_terms(topic))
    if not terms:
        return 0.0, []

    title = normalize_title(paper.title)
    abstract = normalize_title(paper.abstract or "")
    earned = 0.0
    matched: list[str] = []
    for term, weight in sorted(terms.items()):
        factor = _match_factor(term, title, abstract)
        if factor:
            earned += factor * weight
            matched.append(term)
    # Bonus tokens are numerator-only: matching "spatial" helps, but a paper is not penalized
    # for missing it, so a topic with a long name stays as reachable as a short one.
    for token in _bonus_terms(topic, terms):
        earned += _match_factor(token, title, abstract) * _TOKEN_WEIGHT
    return min(1.0, earned / sum(terms.values())), matched


def detect_paper_type(paper: PaperCandidate) -> PaperType:
    """Classify the kind of contribution from cue phrases; unrecognized papers are `other`."""
    haystack = f"{normalize_title(paper.title)} {normalize_title(paper.abstract or '')}"
    for paper_type, cues in _TYPE_CUES:
        if any(cue in haystack for cue in cues):
            return paper_type
    return "other"
