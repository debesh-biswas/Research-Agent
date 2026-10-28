"""Desk answers stay inside the cards that were sent to the model."""

import asyncio
import json

import pytest
from pydantic import BaseModel

from research_agent.desk.ask import DeskLookupError, _context, answer_question, failure_message
from research_agent.models.base import ModelMessage, ModelProviderError, ModelResult
from research_agent.models.router import ModelRouter


class ScriptProvider:
    """A provider that returns one fixed completion, or fails the call."""

    def __init__(self, name: str, text: str, *, fail: bool = False) -> None:
        self.name = name
        self.model = "scripted"
        self.text = text
        self.fail = fail
        self.calls = 0

    async def generate(
        self,
        task: str,
        messages: list[ModelMessage],
        response_schema: type[BaseModel] | None = None,
        *,
        capability: str | None = None,
    ) -> ModelResult:
        del task, messages, response_schema, capability
        self.calls += 1
        if self.fail:
            raise ModelProviderError("unavailable")
        return ModelResult(provider=self.name, model=self.model, text=self.text)


def _shelf() -> dict[str, object]:
    return {
        "live": True,
        "topics": [
            {
                "id": "spatial_intelligence",
                "runs": [
                    {
                        "id": "run-1",
                        "periodStart": "2026-09-18",
                        "periodEnd": "2026-09-28",
                        "executiveSummary": "Named maps won the week.",
                        "developments": [],
                        "contradictions": [],
                        "papers": [
                            {
                                "id": "paper-1",
                                "title": "Language-Conditioned Topological Maps",
                                "contribution": "A named topological map.",
                                "problem": "Grids forget chairs.",
                                "method": "Pose graph.",
                                "results": [],
                                "limitations": ["Twelve apartments."],
                                "claims": [],
                                "relevance": "On topic.",
                                "abstractOnly": False,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_an_unknown_citation_is_dropped() -> None:
    strong = ScriptProvider(
        "nvidia_nim",
        '{"paragraphs": ["The map is named."], "paper_ids": ["paper-1", "invented"]}',
    )
    router = ModelRouter(ScriptProvider("local", "{}"), strong, retries=0)

    reply = asyncio.run(
        answer_question(
            router,
            _shelf(),
            topic_id="spatial_intelligence",
            run_id="run-1",
            question="What is the contribution?",
            paper_id="paper-1",
            max_chars=4000,
        )
    )

    assert reply.paragraphs == ["The map is named."]
    assert reply.cites == [{"paperId": "paper-1", "note": ""}]
    assert reply.fell_back is False
    assert strong.calls == 1


def test_invalid_nim_output_falls_back_to_local() -> None:
    local = ScriptProvider("local", '{"paragraphs": ["Answered locally."], "paper_ids": []}')
    router = ModelRouter(local, ScriptProvider("nvidia_nim", "not json"), retries=0)

    reply = asyncio.run(
        answer_question(
            router,
            _shelf(),
            topic_id="spatial_intelligence",
            run_id="run-1",
            question="Where is this weak?",
            paper_id=None,
            max_chars=4000,
        )
    )

    assert reply.paragraphs == ["Answered locally."]
    assert reply.fell_back is True
    assert reply.note == "Answered by the local model."
    assert local.calls == 1


def test_a_missing_paper_is_not_sent_to_the_model() -> None:
    strong = ScriptProvider("nvidia_nim", "{}")
    router = ModelRouter(ScriptProvider("local", "{}"), strong, retries=0)

    with pytest.raises(DeskLookupError):
        asyncio.run(
            answer_question(
                router,
                _shelf(),
                topic_id="spatial_intelligence",
                run_id="run-1",
                question="What is this?",
                paper_id="missing",
                max_chars=4000,
            )
        )

    assert strong.calls == 0


def _run_with_cards(count: int, method_chars: int) -> dict[str, object]:
    papers = [{"id": f"paper-{index}", "method": "m" * method_chars} for index in range(count)]
    return {"periodStart": "2026-09-18", "periodEnd": "2026-09-28", "papers": papers}


def test_an_over_budget_shelf_drops_whole_cards_and_stays_valid_json() -> None:
    run = _run_with_cards(10, 500)
    allowed = {f"paper-{index}" for index in range(10)}

    text = _context(run, allowed, max_chars=2000)

    assert len(text) <= 2000
    kept = [card["id"] for card in json.loads(text)["papers"]]
    assert kept == [f"paper-{index}" for index in range(len(kept))], "lowest-ranked go first"
    assert 0 < len(kept) < 10


def test_the_only_card_is_kept_even_over_budget() -> None:
    text = _context(_run_with_cards(1, 5000), {"paper-0"}, max_chars=2000)

    assert [card["id"] for card in json.loads(text)["papers"]] == ["paper-0"]


class CapturingProvider(ScriptProvider):
    def __init__(self) -> None:
        super().__init__("nvidia_nim", '{"paragraphs": ["Still the map."], "paper_ids": []}')
        self.prompts: list[str] = []

    async def generate(
        self,
        task: str,
        messages: list[ModelMessage],
        response_schema: type[BaseModel] | None = None,
        *,
        capability: str | None = None,
    ) -> ModelResult:
        self.prompts.append(messages[-1].content)
        return await super().generate(task, messages, response_schema, capability=capability)


def test_a_follow_up_sees_only_the_latest_earlier_turns() -> None:
    strong = CapturingProvider()
    router = ModelRouter(ScriptProvider("local", "{}"), strong, retries=0)
    history = [(f"question {index}", [f"answer {index}"]) for index in range(6)]

    asyncio.run(
        answer_question(
            router,
            _shelf(),
            topic_id="spatial_intelligence",
            run_id="run-1",
            question="And the second one?",
            paper_id=None,
            max_chars=4000,
            history=history,
        )
    )

    prompt = strong.prompts[0]
    assert prompt.startswith("Earlier in this conversation:\nQ: question 2\nA: answer 2\n")
    assert "question 1" not in prompt
    assert "Q: question 5\nA: answer 5\n\nQuestion: And the second one?" in prompt


def test_a_first_question_carries_no_history_block() -> None:
    strong = CapturingProvider()
    router = ModelRouter(ScriptProvider("local", "{}"), strong, retries=0)

    asyncio.run(
        answer_question(
            router,
            _shelf(),
            topic_id="spatial_intelligence",
            run_id="run-1",
            question="What changed?",
            paper_id=None,
            max_chars=4000,
        )
    )

    assert strong.prompts[0].startswith("Question: What changed?")


@pytest.mark.parametrize(
    ("category", "start"),
    [
        ("RATE_LIMIT", "The model is rate-limited"),
        ("MODEL_TIMEOUT", "The model could not be reached"),
        ("MODEL_API_ERROR", "The model answered with an error"),
    ],
)
def test_a_failure_says_what_went_wrong(category: str, start: str) -> None:
    error = ModelProviderError("http://localhost:8080 failed", category)  # type: ignore[arg-type]

    assert failure_message(error).startswith(start)


def _topic_shelf(*runs: dict[str, object]) -> dict[str, object]:
    return {"topics": [{"id": "t", "runs": list(runs)}]}


def _week(run_id: str, summary: str | None, *developments: str) -> dict[str, object]:
    return {
        "id": run_id,
        "periodStart": f"start-{run_id}",
        "periodEnd": f"end-{run_id}",
        "executiveSummary": summary,
        "developments": [{"text": text, "paperIds": ["x"]} for text in developments],
        "papers": [{"id": f"{run_id}-paper", "title": "T"}],
    }


def _sent_context(shelf: dict[str, object], run_id: str, paper_id: str | None = None) -> object:
    strong = CapturingProvider()
    router = ModelRouter(ScriptProvider("local", "{}"), strong, retries=0)
    asyncio.run(
        answer_question(
            router,
            shelf,
            topic_id="t",
            run_id=run_id,
            question="Compared with before?",
            paper_id=paper_id,
            max_chars=20_000,
        )
    )
    return json.loads(strong.prompts[0].split("Cards:\n", 1)[1])


def test_a_week_question_sees_up_to_four_older_weeks_newest_first() -> None:
    shelf = _topic_shelf(
        _week("newer", "Not seen."),
        _week("now", "This week."),
        _week("w1", "Maps won."),
        _week("running", None),
        _week("w2", None, "Only a development."),
        _week("w3", "Three."),
        _week("w4", "Four."),
        _week("w5", "Five is past the window."),
    )

    sent = _sent_context(shelf, "now")

    assert sent["earlier_weeks"] == [  # type: ignore[index]
        {"period": "start-w1 to end-w1", "summary": "Maps won.", "developments": []},
        {
            "period": "start-w2 to end-w2",
            "summary": None,
            "developments": ["Only a development."],
        },
        {"period": "start-w3 to end-w3", "summary": "Three.", "developments": []},
        {"period": "start-w4 to end-w4", "summary": "Four.", "developments": []},
    ]


def test_a_paper_question_and_the_first_week_carry_no_earlier_weeks() -> None:
    shelf = _topic_shelf(_week("now", "This week."), _week("w1", "Maps won."))

    assert "earlier_weeks" not in _sent_context(shelf, "now", "now-paper")  # type: ignore[operator]
    assert "earlier_weeks" not in _sent_context(shelf, "w1")  # type: ignore[operator]


def test_earlier_weeks_have_their_own_budget_and_the_oldest_go_first() -> None:
    run = _run_with_cards(10, 500)
    allowed = {f"paper-{index}" for index in range(10)}
    weeks: list[object] = [{"period": f"w{index}", "summary": "s" * 400} for index in range(4)]

    sent = json.loads(_context(run, allowed, max_chars=2000, weeks=weeks))

    assert [week["period"] for week in sent["earlier_weeks"]] == ["w0"]
    assert len(json.dumps(sent["earlier_weeks"])) <= 2000 // 4
    cards_only = json.loads(_context(run, allowed, max_chars=2000))
    assert sent["papers"] == cards_only["papers"], "weeks never cost this week a card"


def test_no_earlier_week_fitting_leaves_no_earlier_weeks_key() -> None:
    weeks: list[object] = [{"period": "w0", "summary": "s" * 5000}]

    sent = json.loads(_context(_run_with_cards(1, 10), {"paper-0"}, 2000, weeks=weeks))

    assert "earlier_weeks" not in sent


def test_a_long_earlier_week_is_kept_compact() -> None:
    shelf = _topic_shelf(_week("now", "This week."), _week("w1", "x" * 2000, "a", "b", "c", "d"))

    week = _sent_context(shelf, "now")["earlier_weeks"][0]  # type: ignore[index]

    assert len(week["summary"]) == 500
    assert week["developments"] == ["a", "b", "c"]
