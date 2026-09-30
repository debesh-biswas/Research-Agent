"""Answer a desk question from the cards already on the shelf.

NVIDIA NIM serves this when it is configured. The router falls back to the local model after its
retry ceiling. The reply may cite only paper ids that were in the prompt.
"""

import json
import logging

from pydantic import Field

from research_agent.config import StrictModel
from research_agent.desk.shelf import find_run
from research_agent.models.base import ModelMessage, ModelProviderError, ModelValidationError
from research_agent.models.router import ModelRouter

_LOGGER = logging.getLogger(__name__)

PROMPT_VERSION = "desk_ask.v1"
_SYSTEM = (
    "You answer one question about a researcher's weekly reading shelf. Reply with JSON only, "
    'in the form {"paragraphs": ["..."], "paper_ids": ["..."]}. Use only the cards given. '
    "Every paper id must be copied from those cards. If the cards do not cover the question, "
    "say that in one paragraph and return an empty paper_ids list. Do not invent pages, "
    "numbers, papers, or citations. Write plain sentences, with no Markdown headings."
)


class DeskAnswer(StrictModel):
    """The structured reply the model is allowed to produce."""

    paragraphs: list[str] = Field(min_length=1)
    paper_ids: list[str] = Field(default_factory=list)


class DeskReply(StrictModel):
    """A grounded answer, plus which model produced it."""

    paragraphs: list[str] = Field(min_length=1)
    cites: list[dict[str, str]] = Field(default_factory=list)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    fell_back: bool = False
    note: str = ""


class DeskLookupError(Exception):
    """The question named a topic or run that is not on the shelf."""


async def answer_question(
    router: ModelRouter,
    shelf: dict[str, object],
    *,
    topic_id: str,
    run_id: str,
    question: str,
    paper_id: str | None,
    max_chars: int,
) -> DeskReply:
    """Answer from one run, or from one paper on that run when an id is given."""
    run = find_run(shelf, topic_id, run_id)
    if run is None:
        raise DeskLookupError("That run is not on the shelf.")
    papers = _papers(run)
    allowed = {item_id for item_id in papers}
    if paper_id:
        if paper_id not in allowed:
            raise DeskLookupError("That paper is not on this week's shelf.")
        allowed = {paper_id}
    context = _context(run, allowed, max_chars)
    messages = [
        ModelMessage(role="system", content=_SYSTEM),
        ModelMessage(role="user", content=f"Question: {question}\n\nCards:\n{context}"),
    ]
    try:
        result = await router.generate("deep_reasoning", messages, DeskAnswer, task="desk_ask")
    except ModelValidationError:
        _LOGGER.warning(
            "desk answer was not valid JSON; asking the local model",
            extra={"node_name": "desk_ask", "prompt_version": PROMPT_VERSION, "status": "repair"},
        )
        result = await router.generate_local(
            "deep_reasoning", messages, DeskAnswer, task="desk_ask"
        )
    parsed = result.parsed
    if not isinstance(parsed, DeskAnswer):
        raise ModelProviderError("the desk answer was empty")
    paragraphs = [paragraph.strip() for paragraph in parsed.paragraphs if paragraph.strip()]
    if not paragraphs:
        paragraphs = ["The cards do not cover that."]
    cited = [item_id for item_id in parsed.paper_ids if item_id in allowed]
    local = result.fell_back or result.provider == "local"
    return DeskReply(
        paragraphs=paragraphs,
        cites=[{"paperId": item_id, "note": ""} for item_id in cited],
        provider=result.provider,
        model=result.model,
        fell_back=local,
        note="Answered by the local model." if local else "",
    )


def _papers(run: dict[str, object]) -> dict[str, str]:
    raw = run.get("papers")
    if not isinstance(raw, list):
        return {}
    titles: dict[str, str] = {}
    for paper in raw:
        if not isinstance(paper, dict):
            continue
        paper_id = paper.get("id")
        title = paper.get("title")
        if isinstance(paper_id, str) and paper_id and isinstance(title, str):
            titles[paper_id] = title
    return titles


def _context(run: dict[str, object], allowed: set[str], max_chars: int) -> str:
    cards = run.get("papers")
    chosen: list[object] = []
    if isinstance(cards, list):
        for paper in cards:
            if isinstance(paper, dict) and paper.get("id") in allowed:
                chosen.append(_card(paper))
    payload = {
        "period": f"{run.get('periodStart')} to {run.get('periodEnd')}",
        "summary": run.get("executiveSummary"),
        "developments": run.get("developments") if len(allowed) != 1 else [],
        "contradictions": run.get("contradictions") if len(allowed) != 1 else [],
        "papers": chosen,
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _card(paper: dict[str, object]) -> dict[str, object]:
    kept = (
        "id",
        "title",
        "problem",
        "contribution",
        "method",
        "results",
        "limitations",
        "claims",
        "relevance",
        "abstractOnly",
    )
    return {key: paper.get(key) for key in kept}
