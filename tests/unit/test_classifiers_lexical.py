import pytest
from conftest import candidate

from research_agent.classifiers.lexical import (
    PaperType,
    detect_paper_type,
    lexical_score,
    topic_terms,
)
from research_agent.config import TopicSettings


def topic(**overrides: object) -> TopicSettings:
    payload: dict[str, object] = {
        "id": "spatial_intelligence",
        "name": "Spatial Intelligence",
        "keywords": ["embodied navigation"],
    }
    payload.update(overrides)
    return TopicSettings.model_validate(payload)


def test_a_matching_title_scores_higher_than_the_same_words_in_an_abstract() -> None:
    in_title = candidate(title="Spatial Intelligence for Embodied Navigation")
    in_abstract = candidate(
        title="A Robotics Result", abstract="We study spatial intelligence and embodied navigation."
    )

    title_score, title_terms = lexical_score(in_title, topic())
    abstract_score, _ = lexical_score(in_abstract, topic())

    assert title_score > abstract_score > 0
    assert "spatial intelligence" in title_terms


def test_every_score_stays_within_the_unit_interval() -> None:
    saturated = candidate(
        title="Spatial Intelligence Embodied Navigation Spatial Intelligence",
        abstract="spatial intelligence embodied navigation spatial intelligence",
    )

    score, _ = lexical_score(saturated, topic())

    assert 0.0 <= score <= 1.0


def test_an_unrelated_paper_scores_nothing() -> None:
    score, matched = lexical_score(
        candidate(title="Tax Policy in Northern Europe", abstract="A fiscal study."), topic()
    )

    assert (score, matched) == (0.0, [])


def test_scoring_is_deterministic() -> None:
    paper = candidate(abstract="Embodied navigation results.")

    assert lexical_score(paper, topic()) == lexical_score(paper, topic())


def test_a_missing_abstract_and_no_keywords_are_both_tolerated() -> None:
    bare = TopicSettings.model_validate({"id": "quiet", "name": "Quiet"})

    score, matched = lexical_score(candidate(title="Loud Results", abstract=None), bare)

    assert (score, matched) == (0.0, [])


def test_unicode_and_punctuation_still_match() -> None:
    # A non-breaking space and decomposed accents, exactly what NFKC normalization is there for.
    title = "Spatial\u00a0Intelligence: A Re\u0301sume\u0301"

    score, _ = lexical_score(candidate(title=title), topic(name="Spatial Intelligence"))

    assert score > 0


def test_a_near_miss_in_the_title_still_scores() -> None:
    # "spatial intelligences" is not a substring match, but it is well above the fuzzy floor.
    score, matched = lexical_score(candidate(title="On Spatial Intelligences at Scale"), topic())

    assert score > 0
    assert "spatial intelligence" in matched


def test_the_topic_name_outweighs_a_single_keyword() -> None:
    by_name, _ = lexical_score(candidate(title="Spatial Intelligence"), topic())
    by_keyword, _ = lexical_score(candidate(title="Embodied Navigation"), topic())

    assert by_name > by_keyword


def test_topic_terms_deduplicate_a_keyword_repeating_the_name() -> None:
    terms = topic_terms(topic(keywords=["Spatial Intelligence"]))

    assert [term for term, _ in terms].count("spatial intelligence") == 1


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("A Survey of Spatial Reasoning", "survey"),
        ("SpatialBench: A Benchmark for Robots", "benchmark"),
        ("A Large Dataset of Indoor Scenes", "dataset"),
        ("A Case Study in Warehouse Robotics", "application"),
        ("We Propose a Spatial Planner", "method"),
        ("Results", "other"),
    ],
)
def test_paper_type_cues_are_ordered_and_exhaustive(title: str, expected: PaperType) -> None:
    assert detect_paper_type(candidate(title=title, abstract=None)) == expected


def test_paper_type_reads_the_abstract_when_the_title_is_uninformative() -> None:
    assert detect_paper_type(
        candidate(title="Results", abstract="We introduce a novel model.")
    ) == ("method")
