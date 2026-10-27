"""The routing predicates, which are pure functions of state."""

import asyncio
from datetime import date

from research_agent.workflow.graph import (
    _tracked,
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


def test_a_tracked_node_records_its_stage_once_the_run_exists() -> None:
    marked: list[tuple[str, str]] = []

    class Runs:
        def mark_stage(self, run_id: str, stage: str) -> None:
            marked.append((run_id, stage))

    class Services:
        runs = Runs()

    async def node(state: ResearchState) -> dict[str, object]:
        return {"seen": state.run_id}

    tracked = _tracked("classify", node, Services())  # type: ignore[arg-type]
    opening = ResearchState(
        topic_id="t", period_start=date(2026, 9, 1), period_end=date(2026, 9, 8)
    )

    async def call(current: ResearchState) -> object:
        return await tracked(current)

    assert asyncio.run(call(opening)) == {"seen": None}
    assert asyncio.run(call(opening.model_copy(update={"run_id": "r1"}))) == {"seen": "r1"}
    assert marked == [("r1", "classify")]
