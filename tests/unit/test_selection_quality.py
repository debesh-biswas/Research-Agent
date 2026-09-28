from datetime import date

from research_agent.config import SelectionSettings
from research_agent.domain.papers import PaperCandidate, SourceReference
from research_agent.selection.quality import paper_quality_score, ranking_score
from tests.unit.conftest import candidate

AS_OF = date(2026, 9, 28)


def paper(**overrides: object) -> PaperCandidate:
    values: dict[str, object] = {
        "publication_date": date(2026, 9, 27),
        "venue": "CVPR",
        "citation_count": 40,
        "sources": [SourceReference(source="openalex", source_id="W1")],
    }
    values.update(overrides)
    return candidate(**values)


def test_recent_preferred_venue_with_citations_ranks_above_unreviewed_metadata() -> None:
    settings = SelectionSettings()

    strong = paper()
    weak = paper(
        publication_date=None,
        venue=None,
        citation_count=None,
        sources=[SourceReference(source="arxiv", source_id="2401.12345")],
    )

    assert paper_quality_score(strong, settings, AS_OF) > paper_quality_score(weak, settings, AS_OF)


def test_ranking_blends_relevance_with_quality() -> None:
    settings = SelectionSettings()

    assert ranking_score(0.7, paper(), settings, AS_OF) > ranking_score(
        0.7,
        paper(venue=None, citation_count=None),
        settings,
        AS_OF,
    )
