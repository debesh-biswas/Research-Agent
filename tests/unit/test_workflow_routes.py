"""The routing predicates, which are pure functions of state."""

from datetime import date

from research_agent.workflow.graph import (
    after_acquisition,
    after_analysis,
    after_discovery,
    after_selection,
    after_synthesis,
)
from research_agent.workflow.state import ResearchState
from tests.unit.conftest import TOPIC_ID, candidate

START = date(2026, 9, 17)
END = date(2026, 9, 27)


def state(**overrides: object) -> ResearchState:
    payload: dict[str, object] = {
        "topic_id": TOPIC_ID,
        "period_start": START,
        "period_end": END,
        "run_id": "run1",
    }
    payload.update(overrides)
    return ResearchState.model_validate(payload)


def test_discovery_with_candidates_classifies() -> None:
    assert after_discovery(state(candidates=[candidate()])) == "classify"


def test_empty_discovery_broadens_once_then_reports() -> None:
    assert after_discovery(state()) == "broaden"
    assert after_discovery(state(broadened=True)) == "report"


def test_nothing_selected_goes_straight_to_the_report() -> None:
    assert after_selection(state()) == "report"
    assert after_selection(state(selected_ids=["p1"])) == "acquire"


def test_without_a_pdf_parsing_is_skipped() -> None:
    assert after_acquisition(state()) == "analyze"
    assert after_acquisition(state(pdf_paths={"p1": "/tmp/p1.pdf"})) == "parse"


def test_without_an_analysis_synthesis_is_skipped() -> None:
    assert after_analysis(state()) == "report"
    assert after_analysis(state(analyzed_ids=["p1"])) == "synthesize"


def test_without_a_synthesis_ideation_is_skipped() -> None:
    assert after_synthesis(state()) == "report"
    assert after_synthesis(state(synthesized=True)) == "ideate"
