import asyncio
import json
import sqlite3

import httpx
import pytest

from research_agent.config import ApplicationSettings, IdeationSettings, TopicSettings
from research_agent.domain.analysis import SupportedFinding, WeeklySynthesis
from research_agent.ideation.generator import IdeationOutcome, IdeationService
from research_agent.ideation.prompts import GAP_PROMPT_VERSION, IDEA_PROMPT_VERSION
from research_agent.models.router import build_router
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from tests.unit.conftest import TOPIC_ID, mock_client

GAP: dict[str, object] = {
    "title": "No long-horizon benchmark",
    "description": "Existing benchmarks stop at 50 steps.",
    "supporting_paper_ids": ["p1"],
    "confidence": 0.6,
}
IDEA: dict[str, object] = {
    "title": "Persistent map benchmark",
    "hypothesis": "Longer horizons expose memory failures.",
    "motivation": "Current scores saturate.",
    "supporting_paper_ids": ["p1", "p2"],
    "identified_gap": "No long-horizon benchmark",
    "proposed_direction": "Extend ObjectNav episodes to 500 steps.",
    "evaluation_plan": "Compare SPL across horizons; no gap means the hypothesis is wrong.",
    "risks": ["Compute cost"],
}


def topic() -> TopicSettings:
    return TopicSettings.model_validate(
        {"id": TOPIC_ID, "name": "Spatial Intelligence", "keywords": ["embodied navigation"]}
    )


def synthesis() -> WeeklySynthesis:
    return WeeklySynthesis(
        major_developments=[
            SupportedFinding(text="Metric control is benchmarked", supporting_paper_ids=["p1"])
        ],
        common_limitations=[
            SupportedFinding(text="Simulation only", supporting_paper_ids=["p1", "p2"])
        ],
        new_benchmarks=["ObjectNav"],
        paper_ids=["p1", "p2"],
        model_provider="local",
        model_name="qwen",
        prompt_version="weekly_synthesis.v1",
    )


def replying(*contents: str) -> tuple[object, list[dict[str, object]]]:
    sent: list[dict[str, object]] = []
    remaining = list(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        content = remaining.pop(0) if remaining else "{}"
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": content}}]}
        )

    return handler, sent


def gaps_then_ideas(
    gaps: list[dict[str, object]] | None = None, ideas: list[dict[str, object]] | None = None
) -> tuple[object, list[dict[str, object]]]:
    return replying(
        json.dumps({"gaps": gaps if gaps is not None else [GAP]}),
        json.dumps({"ideas": ideas if ideas is not None else [IDEA]}),
    )


@pytest.fixture
def run_id(connection: sqlite3.Connection) -> str:
    return SqliteRunRepository(connection).start(TOPIC_ID, "A").id


def service(
    connection: sqlite3.Connection, handler: object, settings: IdeationSettings | None = None
) -> IdeationService:
    router = build_router(
        mock_client(handler),  # type: ignore[arg-type]
        ApplicationSettings(),
    )
    return IdeationService(router, SqliteResultRepository(connection), settings)


def run(
    connection: sqlite3.Connection,
    run_id: str,
    handler: object,
    settings: IdeationSettings | None = None,
) -> IdeationOutcome:
    return asyncio.run(
        service(connection, handler, settings).generate(topic(), run_id, synthesis())
    )


def test_supported_gaps_and_ideas_are_persisted_with_provenance(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, sent = gaps_then_ideas()

    outcome = run(connection, run_id, handler)

    repository = SqliteResultRepository(connection)
    stored_gaps = repository.gaps_for(run_id)
    stored_ideas = repository.ideas_for(run_id)
    assert [gap.title for gap in stored_gaps] == ["No long-horizon benchmark"]
    assert stored_gaps[0].prompt_version == GAP_PROMPT_VERSION
    assert stored_ideas[0].prompt_version == IDEA_PROMPT_VERSION
    assert stored_ideas[0].supporting_paper_ids == ["p1", "p2"]
    assert (outcome.dropped_gaps, outcome.dropped_ideas) == (0, 0)
    assert "Metric control is benchmarked" in str(sent[0]["messages"])
    assert "No long-horizon benchmark" in str(sent[1]["messages"])


def test_a_gap_citing_an_unknown_paper_is_dropped(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, sent = gaps_then_ideas(gaps=[{**GAP, "supporting_paper_ids": ["ghost"]}])

    outcome = run(connection, run_id, handler)

    assert (outcome.gaps, outcome.dropped_gaps) == ([], 1)
    assert outcome.reason is not None
    assert SqliteResultRepository(connection).gaps_for(run_id) == []
    assert len(sent) == 1, "ideation must not run without a supported gap"


def test_unknown_references_are_pruned_from_a_supported_gap(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, _ = gaps_then_ideas(
        gaps=[{**GAP, "supporting_paper_ids": ["ghost", "p2", "p1", "p1"]}]
    )

    outcome = run(connection, run_id, handler)

    assert outcome.gaps[0].supporting_paper_ids == ["p1", "p2"]


def test_an_idea_for_a_gap_that_was_not_offered_is_dropped(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, _ = gaps_then_ideas(ideas=[{**IDEA, "identified_gap": "Something else entirely"}])

    outcome = run(connection, run_id, handler)

    assert (outcome.ideas, outcome.dropped_ideas) == ([], 1)
    assert SqliteResultRepository(connection).ideas_for(run_id) == []


def test_a_duplicate_idea_is_stored_once(connection: sqlite3.Connection, run_id: str) -> None:
    handler, _ = gaps_then_ideas(ideas=[IDEA, {**IDEA, "title": "  persistent   MAP benchmark "}])

    outcome = run(connection, run_id, handler)

    assert len(outcome.ideas) == 1
    assert outcome.dropped_ideas == 1


def test_the_gap_and_idea_ceilings_are_enforced(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, _ = gaps_then_ideas(
        gaps=[{**GAP, "title": f"Gap {index}"} for index in range(4)],
        ideas=[{**IDEA, "title": f"Idea {index}", "identified_gap": "Gap 0"} for index in range(4)],
    )

    outcome = run(connection, run_id, handler, IdeationSettings(max_gaps=2, max_ideas=1))

    assert (len(outcome.gaps), len(outcome.ideas)) == (2, 1)
    assert (outcome.dropped_gaps, outcome.dropped_ideas) == (2, 3)


def test_an_empty_synthesis_still_produces_a_prompt(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, sent = gaps_then_ideas()
    empty = synthesis().model_copy(
        update={"major_developments": [], "common_limitations": [], "new_benchmarks": []}
    )

    outcome = asyncio.run(service(connection, handler).generate(topic(), run_id, empty))

    assert "recorded no findings" in str(sent[0]["messages"])
    assert outcome.gaps, "an empty synthesis is still a valid input, not an error"


def test_confidence_outside_its_bounds_invalidates_the_reply(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, sent = gaps_then_ideas(gaps=[{**GAP, "confidence": 1.4}])

    outcome = run(connection, run_id, handler)

    assert outcome.gaps == [] and outcome.reason is not None
    assert len(sent) == 1


def test_a_provider_failure_during_gap_detection_stores_nothing(
    connection: sqlite3.Connection, run_id: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "upstream is unwell"})

    outcome = run(connection, run_id, handler)

    assert outcome.gaps == [] and outcome.reason is not None
    assert SqliteResultRepository(connection).gaps_for(run_id) == []


def test_a_provider_failure_during_ideation_keeps_the_gaps(
    connection: sqlite3.Connection, run_id: str
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"role": "assistant", "content": json.dumps({"gaps": [GAP]})}}
                    ]
                },
            )
        return httpx.Response(503, json={"error": "upstream is unwell"})

    outcome = run(connection, run_id, handler)

    assert len(outcome.gaps) == 1 and outcome.ideas == []
    assert outcome.reason is not None and "ideation failed" in outcome.reason
    assert len(SqliteResultRepository(connection).gaps_for(run_id)) == 1


def test_long_input_is_truncated_at_the_configured_limit(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, sent = gaps_then_ideas()
    long_synthesis = synthesis().model_copy(
        update={
            "major_developments": [
                SupportedFinding(text="word " * 500, supporting_paper_ids=["p1"])
            ]
        }
    )

    asyncio.run(
        service(connection, handler, IdeationSettings(max_input_chars=400)).generate(
            topic(), run_id, long_synthesis
        )
    )

    assert "input truncated" in str(sent[0]["messages"])
