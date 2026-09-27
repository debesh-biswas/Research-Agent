import asyncio
import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from research_agent.analysis.analyzer import PaperAnalyzer
from research_agent.analysis.prompts import PROMPT_VERSION
from research_agent.config import AnalysisSettings, ApplicationSettings, TopicSettings
from research_agent.domain.documents import ParsedPaper, ParsedSection
from research_agent.domain.papers import PaperCandidate
from research_agent.models.router import build_router
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from tests.unit.conftest import TOPIC_ID, candidate, mock_client

DRAFT: dict[str, object] = {
    "research_problem": "Agents cannot reason about unseen rooms.",
    "main_contribution": "A persistent spatial memory module.",
    "method": "A transformer over a metric map.",
    "datasets": ["HM3D"],
    "benchmarks": ["ObjectNav"],
    "experimental_setup": "Ten episodes per scene.",
    "main_results": ["+7 SPL over the baseline"],
    "strengths": ["Ablations are thorough"],
    "limitations": ["Simulation only"],
    "key_claims": [
        {
            "text": "Memory improves navigation",
            "source_section": "Results",
            "page": 7,
            "evidence_excerpt": "SPL rises from 0.51 to 0.58.",
        }
    ],
    "related_work": ["Neural SLAM"],
    "topic_relevance": "Directly on topic.",
}


def topic() -> TopicSettings:
    return TopicSettings.model_validate(
        {"id": TOPIC_ID, "name": "Spatial Intelligence", "keywords": ["embodied navigation"]}
    )


def parsed(paper_id: str, body: str = "We introduce a spatial memory module.") -> ParsedPaper:
    return ParsedPaper(
        paper_id=paper_id,
        source_pdf_path="/tmp/paper.pdf",
        title="A Parsed Paper",
        sections=[
            ParsedSection(title="Introduction", text="Background."),
            ParsedSection(title="Results", text=body, page=7),
        ],
        parser_name="fake",
        parser_version="1.0",
    )


def replying(*contents: str) -> tuple[object, list[dict[str, object]]]:
    """A transport answering with each content in turn, recording every request body."""
    sent: list[dict[str, object]] = []
    remaining = list(contents)

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        content = remaining.pop(0) if remaining else json.dumps(DRAFT)
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": content}}]}
        )

    return handler, sent


def failing(status: int = 500) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        if "efgh" in request.content.decode("utf-8"):
            return httpx.Response(status, json={"error": "upstream is unwell"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps(DRAFT)}}]},
        )

    return handler


@pytest.fixture
def run_id(connection: sqlite3.Connection) -> str:
    return SqliteRunRepository(connection).start(TOPIC_ID, "A").id


def stored(connection: sqlite3.Connection, doi: str = "10.1234/abcd") -> PaperCandidate:
    repository = SqlitePaperRepository(connection)
    paper_id = repository.upsert(candidate(doi=doi, title=f"Spatial Memory {doi}"))
    paper = repository.get(paper_id)
    assert paper is not None
    return paper


def analyzer(
    connection: sqlite3.Connection,
    tmp_path: Path,
    handler: object,
    settings: AnalysisSettings | None = None,
    concurrency: int = 2,
) -> PaperAnalyzer:
    router = build_router(
        mock_client(handler),  # type: ignore[arg-type]
        ApplicationSettings(),
    )
    return PaperAnalyzer(
        router,
        SqliteResultRepository(connection),
        SqlitePaperRepository(connection),
        LocalArtifactStore(tmp_path / "artifacts"),
        settings,
        concurrency,
    )


def test_full_text_becomes_a_persisted_analysis_and_a_card(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    paper = stored(connection)
    handler, _ = replying(json.dumps(DRAFT))

    outcome = asyncio.run(
        analyzer(connection, tmp_path, handler).analyze(
            paper, parsed(paper.canonical_id or ""), topic(), run_id
        )
    )

    assert (outcome.status, outcome.abstract_only) == ("analyzed", False)
    analysis = SqliteResultRepository(connection).analysis_for(paper.canonical_id or "")
    assert analysis is not None
    assert analysis.prompt_version == PROMPT_VERSION
    assert (analysis.model_provider, analysis.main_contribution) == (
        "local",
        "A persistent spatial memory module.",
    )
    assert outcome.path is not None
    assert "## Main contribution" in Path(outcome.path).read_text(encoding="utf-8")


def test_a_paper_without_parsed_text_is_marked_abstract_only(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    paper = stored(connection)
    handler, sent = replying(json.dumps(DRAFT))

    outcome = asyncio.run(
        analyzer(connection, tmp_path, handler).analyze(paper, None, topic(), run_id)
    )

    assert (outcome.status, outcome.abstract_only) == ("analyzed", True)
    analysis = SqliteResultRepository(connection).analysis_for(paper.canonical_id or "")
    assert analysis is not None and analysis.abstract_only
    prompt = str(sent[0]["messages"])
    assert "no parsed full text is available" in prompt


def test_a_claim_citing_a_real_section_keeps_its_provenance(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    paper = stored(connection)
    handler, _ = replying(json.dumps(DRAFT))

    asyncio.run(
        analyzer(connection, tmp_path, handler).analyze(
            paper, parsed(paper.canonical_id or ""), topic(), run_id
        )
    )

    analysis = SqliteResultRepository(connection).analysis_for(paper.canonical_id or "")
    assert analysis is not None
    assert (analysis.key_claims[0].source_section, analysis.key_claims[0].page) == ("Results", 7)


def test_a_claim_citing_a_missing_section_loses_its_provenance(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    paper = stored(connection)
    invented = {**DRAFT, "key_claims": [{"text": "Memory helps", "source_section": "Section 9"}]}
    handler, _ = replying(json.dumps(invented))

    asyncio.run(
        analyzer(connection, tmp_path, handler).analyze(
            paper, parsed(paper.canonical_id or ""), topic(), run_id
        )
    )

    analysis = SqliteResultRepository(connection).analysis_for(paper.canonical_id or "")
    assert analysis is not None
    claim = analysis.key_claims[0]
    assert claim.text == "Memory helps"
    assert (claim.source_section, claim.page) == (None, None)


def test_claims_are_dropped_when_the_configuration_excludes_them(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    paper = stored(connection)
    handler, sent = replying(json.dumps(DRAFT))
    settings = AnalysisSettings(include_claims=False)

    asyncio.run(
        analyzer(connection, tmp_path, handler, settings).analyze(paper, None, topic(), run_id)
    )

    analysis = SqliteResultRepository(connection).analysis_for(paper.canonical_id or "")
    assert analysis is not None and analysis.key_claims == []
    assert "empty list" in str(sent[0]["messages"])


def test_a_stored_analysis_short_circuits_unless_forced(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    paper = stored(connection)
    handler, sent = replying()
    analysis = analyzer(connection, tmp_path, handler)
    asyncio.run(analysis.analyze(paper, None, topic(), run_id))

    cached = asyncio.run(analysis.analyze(paper, None, topic(), run_id))
    forced = asyncio.run(analysis.analyze(paper, None, topic(), run_id, force=True))

    assert (cached.status, forced.status) == ("cached", "analyzed")
    assert len(sent) == 2


def test_a_successful_analysis_marks_the_paper_analyzed(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    paper = stored(connection)
    handler, _ = replying()

    asyncio.run(analyzer(connection, tmp_path, handler).analyze(paper, None, topic(), run_id))

    paper_id = paper.canonical_id or ""
    assert SqlitePaperRepository(connection).analyzed_unchanged([paper_id]) == {paper_id}


def test_one_provider_failure_leaves_the_other_papers_analyzed(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    first = stored(connection)
    second = stored(connection, doi="10.1234/efgh")

    outcomes = asyncio.run(
        analyzer(connection, tmp_path, failing()).analyze_many([first, second], {}, topic(), run_id)
    )

    assert [outcome.status for outcome in outcomes] == ["analyzed", "failed"]
    assert outcomes[1].reason is not None


def test_malformed_output_fails_the_paper_without_a_second_call(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    paper = stored(connection)
    handler, sent = replying("not json at all")

    outcome = asyncio.run(
        analyzer(connection, tmp_path, handler).analyze(paper, None, topic(), run_id)
    )

    assert outcome.status == "failed"
    assert len(sent) == 1
    assert SqliteResultRepository(connection).analysis_for(paper.canonical_id or "") is None


def test_long_text_is_truncated_at_the_configured_limit(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    paper = stored(connection)
    handler, sent = replying()
    settings = AnalysisSettings(max_input_chars=200)

    asyncio.run(
        analyzer(connection, tmp_path, handler, settings).analyze(
            paper, parsed(paper.canonical_id or "", body="word " * 500), topic(), run_id
        )
    )

    prompt = str(sent[0]["messages"])
    assert "text truncated" in prompt
    assert prompt.count("word") < 200


def test_analysis_runs_no_more_than_the_configured_concurrency(
    connection: sqlite3.Connection, tmp_path: Path, run_id: str
) -> None:
    papers = [stored(connection, doi=f"10.1234/paper{index}") for index in range(4)]
    live = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.01)
        live -= 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps(DRAFT)}}]},
        )

    outcomes = asyncio.run(
        analyzer(connection, tmp_path, handler, concurrency=2).analyze_many(
            papers, {}, topic(), run_id
        )
    )

    assert [outcome.status for outcome in outcomes] == ["analyzed"] * 4
    assert peak <= 2
