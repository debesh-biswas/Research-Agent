import asyncio
import json
import re
import sqlite3
from datetime import date

import httpx
import pytest

from research_agent.config import ApplicationSettings, SynthesisSettings, TopicSettings
from research_agent.domain.analysis import PaperAnalysis
from research_agent.models.router import build_router
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from research_agent.synthesis.prompts import PROMPT_VERSION
from research_agent.synthesis.synthesizer import SynthesisOutcome, WeeklySynthesizer
from tests.unit.conftest import TOPIC_ID, mock_client

START = date(2026, 9, 17)
END = date(2026, 9, 27)


def analysis(paper_id: str, **overrides: object) -> PaperAnalysis:
    payload: dict[str, object] = {
        "paper_id": paper_id,
        "research_problem": "Agents cannot reason about unseen rooms.",
        "main_contribution": f"Contribution of {paper_id}.",
        "method": "A transformer over a metric map.",
        "datasets": ["HM3D"],
        "benchmarks": ["ObjectNav"],
        "main_results": ["+7 SPL over the baseline"],
        "limitations": ["Simulation only"],
        "topic_relevance": "Directly on topic.",
        "model_provider": "local",
        "model_name": "qwen",
        "prompt_version": "paper_analysis.v1",
    }
    payload.update(overrides)
    return PaperAnalysis.model_validate(payload)


def draft(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "major_developments": [
            {"text": "Metric control is now benchmarked", "supporting_paper_ids": ["p1", "p2"]}
        ],
        "emerging_directions": [
            {"text": "Active perception budgets", "supporting_paper_ids": ["p2"]}
        ],
        "methods_gaining_attention": [],
        "contradictions": [],
        "common_limitations": [{"text": "Simulation only", "supporting_paper_ids": ["p1"]}],
        "new_datasets": ["HM3D"],
        "new_benchmarks": ["ObjectNav"],
        "changes_from_history": [],
    }
    payload.update(overrides)
    return payload


def topic() -> TopicSettings:
    return TopicSettings.model_validate(
        {"id": TOPIC_ID, "name": "Spatial Intelligence", "keywords": ["embodied navigation"]}
    )


def replying(*contents: str) -> tuple[object, list[dict[str, object]]]:
    sent: list[dict[str, object]] = []
    remaining = list(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        content = remaining.pop(0) if remaining else json.dumps(draft())
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": content}}]}
        )

    return handler, sent


@pytest.fixture
def run_id(connection: sqlite3.Connection) -> str:
    return SqliteRunRepository(connection).start(TOPIC_ID, "A").id


def synthesizer(
    connection: sqlite3.Connection, handler: object, settings: SynthesisSettings | None = None
) -> WeeklySynthesizer:
    router = build_router(
        mock_client(handler),  # type: ignore[arg-type]
        ApplicationSettings(),
    )
    return WeeklySynthesizer(router, SqliteResultRepository(connection), settings)


def run(
    synthesis: WeeklySynthesizer,
    run_id: str,
    analyses: list[PaperAnalysis],
    titles: dict[str, str] | None = None,
) -> SynthesisOutcome:
    return asyncio.run(
        synthesis.synthesize(
            topic(),
            run_id,
            analyses,
            titles or {item.paper_id: f"Title of {item.paper_id}" for item in analyses},
            START,
            END,
        )
    )


def test_a_synthesis_is_persisted_with_its_provenance(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, sent = replying()

    outcome = run(synthesizer(connection, handler), run_id, [analysis("p1"), analysis("p2")])

    assert outcome.synthesis is not None
    stored = SqliteResultRepository(connection).recent_syntheses(TOPIC_ID)
    assert len(stored) == 1
    assert stored[0].prompt_version == PROMPT_VERSION
    assert (stored[0].model_provider, stored[0].paper_ids) == ("local", ["p1", "p2"])
    assert stored[0].major_developments[0].supporting_paper_ids == ["p1", "p2"]
    prompt = str(sent[0]["messages"])
    assert "Title of p1" in prompt and "Contribution of p2" in prompt


def test_a_single_analysis_still_synthesizes(connection: sqlite3.Connection, run_id: str) -> None:
    handler, _ = replying(json.dumps(draft(major_developments=[])))

    outcome = run(synthesizer(connection, handler), run_id, [analysis("p1")])

    assert outcome.synthesis is not None


def test_no_analyses_means_no_call_and_no_synthesis(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, sent = replying()

    outcome = run(synthesizer(connection, handler), run_id, [])

    assert outcome.synthesis is None
    assert sent == []
    assert SqliteResultRepository(connection).recent_syntheses(TOPIC_ID) == []


def test_a_finding_citing_an_unknown_paper_is_dropped(
    connection: sqlite3.Connection, run_id: str
) -> None:
    invented = draft(
        major_developments=[{"text": "Invented trend", "supporting_paper_ids": ["ghost"]}]
    )
    handler, _ = replying(json.dumps(invented))

    outcome = run(synthesizer(connection, handler), run_id, [analysis("p1"), analysis("p2")])

    stored = SqliteResultRepository(connection).recent_syntheses(TOPIC_ID)[0]
    assert stored.major_developments == []
    assert outcome.dropped_findings == 1


def test_unknown_references_are_pruned_from_a_supported_finding(
    connection: sqlite3.Connection, run_id: str
) -> None:
    mixed = draft(
        major_developments=[{"text": "Real trend", "supporting_paper_ids": ["ghost", "p2", "p1"]}]
    )
    handler, _ = replying(json.dumps(mixed))

    run(synthesizer(connection, handler), run_id, [analysis("p1"), analysis("p2")])

    stored = SqliteResultRepository(connection).recent_syntheses(TOPIC_ID)[0]
    assert stored.major_developments[0].supporting_paper_ids == ["p1", "p2"]


def test_contradictions_and_repeated_evidence_survive(
    connection: sqlite3.Connection, run_id: str
) -> None:
    contested = draft(
        contradictions=[
            {"text": "p1 and p2 disagree on transfer", "supporting_paper_ids": ["p1", "p2"]}
        ],
        methods_gaining_attention=[
            {"text": "Metric control", "supporting_paper_ids": ["p1", "p1", "p2"]}
        ],
    )
    handler, _ = replying(json.dumps(contested))

    run(synthesizer(connection, handler), run_id, [analysis("p1"), analysis("p2")])

    stored = SqliteResultRepository(connection).recent_syntheses(TOPIC_ID)[0]
    assert stored.contradictions[0].supporting_paper_ids == ["p1", "p2"]
    assert stored.methods_gaining_attention[0].supporting_paper_ids == ["p1", "p2"]


def test_without_history_the_prompt_says_so(connection: sqlite3.Connection, run_id: str) -> None:
    handler, sent = replying()

    outcome = run(synthesizer(connection, handler), run_id, [analysis("p1")])

    assert "No previous synthesis exists" in str(sent[0]["messages"])
    assert outcome.synthesis is not None and outcome.synthesis.history_periods == 0


def test_history_is_limited_to_the_configured_window(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, sent = replying(*[json.dumps(draft())] * 7)
    synthesis = synthesizer(connection, handler)
    for _ in range(6):
        run(synthesis, run_id, [analysis("p1"), analysis("p2")])

    outcome = run(synthesis, run_id, [analysis("p1"), analysis("p2")])

    assert outcome.synthesis is not None and outcome.synthesis.history_periods == 4
    assert str(sent[-1]["messages"]).count("Period -") == 4


def test_a_provider_failure_leaves_no_synthesis(
    connection: sqlite3.Connection, run_id: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "upstream is unwell"})

    outcome = run(synthesizer(connection, handler), run_id, [analysis("p1")])

    assert outcome.synthesis is None and outcome.reason is not None
    assert SqliteResultRepository(connection).recent_syntheses(TOPIC_ID) == []


def test_malformed_output_leaves_no_synthesis(connection: sqlite3.Connection, run_id: str) -> None:
    handler, sent = replying("not json")

    outcome = run(synthesizer(connection, handler), run_id, [analysis("p1")])

    assert outcome.synthesis is None
    assert len(sent) == 1


def test_a_long_week_is_truncated_at_the_configured_limit(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, sent = replying()
    analyses = [analysis(f"p{index}", method="word " * 200) for index in range(20)]

    run(synthesizer(connection, handler, SynthesisSettings(max_input_chars=500)), run_id, analyses)

    assert "input truncated" in str(sent[0]["messages"])


def test_the_same_inputs_store_identical_references(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, _ = replying(json.dumps(draft()), json.dumps(draft()))
    synthesis = synthesizer(connection, handler)
    analyses = [analysis("p2"), analysis("p1")]

    run(synthesis, run_id, analyses)
    run(synthesis, run_id, list(reversed(analyses)))

    stored = SqliteResultRepository(connection).recent_syntheses(TOPIC_ID)
    assert stored[0].paper_ids == stored[1].paper_ids == ["p1", "p2"]


def batching_handler(
    fail: set[str] | None = None,
) -> tuple[object, list[str]]:
    """Answer batches with a finding citing their own papers, and merges with one combined one.

    `fail` names prompt kinds ("batch:<first id>" or "merge") that get an empty reply.
    """
    prompts: list[str] = []
    failing = fail or set()

    def handler(request: httpx.Request) -> httpx.Response:
        prompt = json.loads(request.content)["messages"][-1]["content"]
        prompts.append(prompt)
        ids = re.findall(r"- id: (\S+)", prompt)
        if "Partial syntheses" in prompt:
            kind = "merge"
            cited = sorted(set(re.findall(r"\[([^\]]+)\]", prompt)))
            body = draft(
                major_developments=[
                    {"text": "Merged week", "supporting_paper_ids": ", ".join(cited).split(", ")}
                ],
                changes_from_history=["Compared once, at the merge"],
            )
        else:
            kind = f"batch:{ids[0]}"
            body = draft(
                major_developments=[{"text": f"Batch from {ids[0]}", "supporting_paper_ids": ids}],
                emerging_directions=[],
                common_limitations=[{"text": "Simulation only", "supporting_paper_ids": ids[:1]}],
            )
        content = "" if kind in failing else json.dumps(body)
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": content}}]}
        )

    return handler, prompts


def week(count: int) -> list[PaperAnalysis]:
    return [analysis(f"p{index:02d}") for index in range(count)]


SMALL_BUDGET = SynthesisSettings(max_input_chars=1500)


def test_a_week_that_fits_is_still_one_call(connection: sqlite3.Connection, run_id: str) -> None:
    handler, prompts = batching_handler()

    outcome = run(synthesizer(connection, handler), run_id, week(2))

    assert (outcome.batches, len(prompts)) == (1, 1)
    assert "one batch of a larger week" not in prompts[0]


def test_a_large_week_is_batched_so_every_paper_reaches_the_model_then_merged(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, prompts = batching_handler()
    papers = week(9)

    outcome = run(synthesizer(connection, handler, SMALL_BUDGET), run_id, papers)

    batch_prompts, merge_prompts = prompts[:-1], prompts[-1:]
    assert outcome.batches == len(batch_prompts) > 1
    assert all(len(prompt) <= SMALL_BUDGET.max_input_chars for prompt in prompts)
    seen = [found for prompt in batch_prompts for found in re.findall(r"- id: (\S+)", prompt)]
    assert seen == [paper.paper_id for paper in papers], "each paper in exactly one batch"
    assert all("leave changes_from_history empty" in prompt for prompt in batch_prompts)
    assert "Partial syntheses" in merge_prompts[0] and "Batch from p00" in merge_prompts[0]
    assert outcome.synthesis is not None
    (merged,) = outcome.synthesis.major_developments
    assert merged.text == "Merged week"
    assert merged.supporting_paper_ids == sorted(paper.paper_id for paper in papers)
    assert outcome.synthesis.changes_from_history == ["Compared once, at the merge"]


def test_a_failed_merge_keeps_the_batch_findings(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, _ = batching_handler(fail={"merge"})

    outcome = run(synthesizer(connection, handler, SMALL_BUDGET), run_id, week(9))

    assert outcome.synthesis is not None
    texts = [finding.text for finding in outcome.synthesis.major_developments]
    assert texts[0] == "Batch from p00" and len(set(texts)) == len(texts) == outcome.batches
    assert texts == sorted(texts), "one finding per batch, in batch order"
    assert [f.text for f in outcome.synthesis.common_limitations] == ["Simulation only"]


def test_a_failed_batch_leaves_the_others_and_all_failing_is_reported(
    connection: sqlite3.Connection, run_id: str
) -> None:
    handler, prompts = batching_handler(fail={"batch:p00"})

    outcome = run(synthesizer(connection, handler, SMALL_BUDGET), run_id, week(9))

    assert outcome.synthesis is not None
    assert "Batch from p00" not in prompts[-1] and "Batch from" in prompts[-1]

    everything = {f"batch:p{index:02d}" for index in range(9)}
    handler, _ = batching_handler(fail=everything)
    failed = run(synthesizer(connection, handler, SMALL_BUDGET), run_id, week(9))
    assert failed.synthesis is None and failed.reason and "every batch failed" in failed.reason


def test_the_fallback_takes_each_batchs_best_in_turn_up_to_the_cap() -> None:
    from research_agent.domain.analysis import SynthesisDraft
    from research_agent.synthesis.synthesizer import _union

    def batch(name: str) -> SynthesisDraft:
        return SynthesisDraft.model_validate(
            {
                "major_developments": [
                    {"text": f"{name}{rank}", "supporting_paper_ids": ["p"]} for rank in range(6)
                ],
                "new_datasets": [f"{name}-data", "shared"],
            }
        )

    merged = _union([batch("a"), batch("b")])

    assert [f.text for f in merged.major_developments] == [
        "a0",
        "b0",
        "a1",
        "b1",
        "a2",
        "b2",
        "a3",
        "b3",
    ]
    assert merged.new_datasets == ["a-data", "b-data", "shared"]


def test_batches_keep_thinking_and_the_merge_keeps_its_output_budget(
    connection: sqlite3.Connection, run_id: str
) -> None:
    bodies: list[dict[str, object]] = []
    answer, _ = batching_handler()

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return answer(request)  # type: ignore[operator, no-any-return]

    settings = ApplicationSettings.model_validate(
        {"models": {"local": {"disable_thinking": True, "thinking_capabilities": ["synthesis"]}}}
    )
    router = build_router(mock_client(handler), settings)
    synthesis = WeeklySynthesizer(router, SqliteResultRepository(connection), SMALL_BUDGET)

    outcome = run(synthesis, run_id, week(9))

    assert outcome.batches > 1
    *batch_bodies, merge_body = bodies
    assert all("chat_template_kwargs" not in body for body in batch_bodies), "thinking on"
    assert merge_body["chat_template_kwargs"] == {"enable_thinking": False}
