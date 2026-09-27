"""Parsing orchestration: caching, storage, and failure isolation around any parser backend.

The backend itself is a pure translation (see ``docling_parser``). Everything that has to be true
regardless of backend — a parse failure never ends a run, an unchanged PDF is never re-parsed —
lives here.
"""

import json
import logging
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field

from research_agent.config import StrictModel
from research_agent.domain.documents import ParsedPaper
from research_agent.storage.artifacts import ArtifactStore
from research_agent.storage.papers import PaperRepository

_LOGGER = logging.getLogger(__name__)

ParseStatus = Literal["parsed", "cached", "failed"]


class ParseOutcome(StrictModel):
    """What parsing did with one paper.

    A failure still leaves the paper eligible for abstract-only analysis in F13.
    """

    paper_id: str = Field(min_length=1)
    status: ParseStatus
    path: str | None = None
    sections: int = Field(default=0, ge=0)
    reason: str | None = None


class DocumentParser(Protocol):
    """One parsing backend, independent of how its output is stored."""

    @property
    def name(self) -> str: ...

    def parse(self, pdf_path: Path, paper_id: str) -> ParsedPaper: ...


class ParsingService:
    """Parse stored PDFs into Markdown and structured JSON, once each, without ever raising."""

    def __init__(
        self,
        parser: DocumentParser,
        store: ArtifactStore,
        papers: PaperRepository,
    ) -> None:
        self._parser = parser
        self._store = store
        self._papers = papers

    def parse_many(
        self, paper_ids: list[str], topic_id: str, run_id: str | None = None, force: bool = False
    ) -> list[ParseOutcome]:
        return [self.parse(paper_id, topic_id, run_id, force) for paper_id in paper_ids]

    def parse(
        self, paper_id: str, topic_id: str, run_id: str | None = None, force: bool = False
    ) -> ParseOutcome:
        """Parse one stored PDF; any backend failure becomes a recorded outcome."""
        files = self._papers.files_for(paper_id)
        pdf = files.get("pdf")
        if pdf is None:
            return ParseOutcome(paper_id=paper_id, status="failed", reason="no stored PDF")
        if not Path(pdf).is_file():
            return ParseOutcome(
                paper_id=paper_id, status="failed", reason=f"stored PDF is missing: {pdf}"
            )

        name = f"{paper_id}.md"
        if not force and "parsed" in files and self._store.exists(topic_id, "parsed", name):
            return ParseOutcome(
                paper_id=paper_id,
                status="cached",
                path=str(self._store.path_for(topic_id, "parsed", name)),
            )

        try:
            parsed = self._parser.parse(Path(pdf), paper_id)
        except Exception as error:
            _LOGGER.warning(
                "pdf parsing failed; the paper stays available for abstract-only analysis",
                extra={
                    "paper_id": paper_id,
                    "topic_id": topic_id,
                    "node_name": "parse",
                    "error_type": "PDF_PARSE_ERROR",
                    "status": "failed",
                },
            )
            return ParseOutcome(paper_id=paper_id, status="failed", reason=str(error))

        return self._store_parsed(parsed, topic_id, run_id)

    def _store_parsed(self, parsed: ParsedPaper, topic_id: str, run_id: str | None) -> ParseOutcome:
        """Write the Markdown a human reads and the JSON the analyzer reads, then record it."""
        markdown = parsed.text
        path = self._store.write_text(topic_id, "parsed", f"{parsed.paper_id}.md", markdown)
        self._store.write_text(
            topic_id, "parsed", f"{parsed.paper_id}.json", parsed.model_dump_json(indent=2)
        )
        self._papers.record_file(
            parsed.paper_id, "parsed", str(path), len(markdown.encode("utf-8")), "", run_id
        )
        return ParseOutcome(
            paper_id=parsed.paper_id,
            status="parsed",
            path=str(path),
            sections=len(parsed.sections),
        )

    def load(self, paper_id: str, topic_id: str) -> ParsedPaper | None:
        """Read back a stored parse, the input F13 analysis prefers over an abstract."""
        return load_parsed(self._store, paper_id, topic_id)


def load_parsed(store: ArtifactStore, paper_id: str, topic_id: str) -> ParsedPaper | None:
    """Read a stored parse without a parser, which is all analysis needs.

    A parse that will not validate is treated as absent, so a corrupt artifact degrades to
    abstract-only analysis instead of failing the paper.
    """
    name = f"{paper_id}.json"
    if not store.exists(topic_id, "parsed", name):
        return None
    try:
        return ParsedPaper.model_validate(json.loads(store.read_text(topic_id, "parsed", name)))
    except (ValueError, OSError):
        return None
