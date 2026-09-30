"""Desk answers stay inside the cards that were sent to the model."""

import asyncio

import pytest
from pydantic import BaseModel

from research_agent.desk.ask import DeskLookupError, answer_question
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
    ) -> ModelResult:
        del task, messages, response_schema
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
