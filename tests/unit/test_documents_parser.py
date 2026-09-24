import sqlite3
from pathlib import Path

import pytest

from research_agent.documents.parser import ParsingService
from research_agent.domain.documents import ParsedPaper, ParsedSection
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.papers import SqlitePaperRepository
from tests.unit.conftest import TOPIC_ID, candidate

PAPER_ID = "doi_10_1234_abcd"


class FakeParser:
    """A parser that returns fixed sections, or fails, without touching Docling."""

    name = "fake"

    def __init__(self, error: Exception | None = None, sections: int = 2) -> None:
        self._error = error
        self._sections = sections
        self.calls = 0

    def parse(self, pdf_path: Path, paper_id: str) -> ParsedPaper:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return ParsedPaper(
            paper_id=paper_id,
            source_pdf_path=str(pdf_path),
            title="A Parsed Paper",
            sections=[
                ParsedSection(title=f"Section {index}", text=f"Body {index}", page=index + 1)
                for index in range(self._sections)
            ],
            parser_name=self.name,
            parser_version="1.0",
        )


@pytest.fixture
def stored_pdf(connection: sqlite3.Connection, tmp_path: Path) -> Path:
    """A paper with a real file on disk and a `paper_files` row pointing at it."""
    repository = SqlitePaperRepository(connection)
    paper_id = repository.upsert(candidate(doi="10.1234/abcd"))
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")
    repository.record_file(paper_id, "pdf", str(pdf), pdf.stat().st_size, "abc123")
    return pdf


def service(
    connection: sqlite3.Connection, tmp_path: Path, parser: FakeParser | None = None
) -> ParsingService:
    return ParsingService(
        parser or FakeParser(),
        LocalArtifactStore(tmp_path / "artifacts"),
        SqlitePaperRepository(connection),
    )


def test_a_pdf_becomes_markdown_json_and_a_recorded_file(
    connection: sqlite3.Connection, tmp_path: Path, stored_pdf: Path
) -> None:
    outcome = service(connection, tmp_path).parse(PAPER_ID, TOPIC_ID)

    assert (outcome.status, outcome.sections) == ("parsed", 2)
    assert outcome.path is not None and outcome.path.endswith(f"{PAPER_ID}.md")
    markdown = Path(outcome.path).read_text(encoding="utf-8")
    assert "## Section 0" in markdown and "Body 1" in markdown
    assert Path(outcome.path).with_suffix(".json").is_file()
    assert SqlitePaperRepository(connection).files_for(PAPER_ID)["parsed"] == outcome.path


def test_a_second_pass_reuses_the_stored_parse(
    connection: sqlite3.Connection, tmp_path: Path, stored_pdf: Path
) -> None:
    parser = FakeParser()
    parsing = service(connection, tmp_path, parser)
    parsing.parse(PAPER_ID, TOPIC_ID)

    outcome = parsing.parse(PAPER_ID, TOPIC_ID)

    assert outcome.status == "cached"
    assert parser.calls == 1


def test_force_re_parses_an_already_parsed_paper(
    connection: sqlite3.Connection, tmp_path: Path, stored_pdf: Path
) -> None:
    parser = FakeParser()
    parsing = service(connection, tmp_path, parser)
    parsing.parse(PAPER_ID, TOPIC_ID)

    outcome = parsing.parse(PAPER_ID, TOPIC_ID, force=True)

    assert outcome.status == "parsed"
    assert parser.calls == 2


def test_a_failing_parser_is_reported_not_raised(
    connection: sqlite3.Connection, tmp_path: Path, stored_pdf: Path
) -> None:
    parsing = service(connection, tmp_path, FakeParser(error=RuntimeError("corrupt xref table")))

    outcome = parsing.parse(PAPER_ID, TOPIC_ID)

    assert outcome.status == "failed"
    assert outcome.reason is not None and "corrupt xref" in outcome.reason
    assert "parsed" not in SqlitePaperRepository(connection).files_for(PAPER_ID)


def test_a_paper_with_no_stored_pdf_fails_cleanly(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    SqlitePaperRepository(connection).upsert(candidate(doi="10.1234/abcd"))

    outcome = service(connection, tmp_path).parse(PAPER_ID, TOPIC_ID)

    assert (outcome.status, outcome.reason) == ("failed", "no stored PDF")


def test_a_missing_file_on_disk_fails_cleanly(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    repository = SqlitePaperRepository(connection)
    repository.upsert(candidate(doi="10.1234/abcd"))
    repository.record_file(PAPER_ID, "pdf", str(tmp_path / "gone.pdf"), 10, "abc")

    outcome = service(connection, tmp_path).parse(PAPER_ID, TOPIC_ID)

    assert outcome.status == "failed"
    assert outcome.reason is not None and "missing" in outcome.reason


def test_one_failure_does_not_stop_the_batch(
    connection: sqlite3.Connection, tmp_path: Path, stored_pdf: Path
) -> None:
    repository = SqlitePaperRepository(connection)
    other = repository.upsert(candidate(doi="10.1234/efgh"))

    outcomes = service(connection, tmp_path).parse_many([PAPER_ID, other], TOPIC_ID)

    assert [outcome.status for outcome in outcomes] == ["parsed", "failed"]


def test_a_stored_parse_can_be_read_back(
    connection: sqlite3.Connection, tmp_path: Path, stored_pdf: Path
) -> None:
    parsing = service(connection, tmp_path)
    parsing.parse(PAPER_ID, TOPIC_ID)

    parsed = parsing.load(PAPER_ID, TOPIC_ID)

    assert parsed is not None
    assert parsed.parser_name == "fake"
    assert len(parsed.sections) == 2


def test_loading_an_unparsed_paper_returns_nothing(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    assert service(connection, tmp_path).load(PAPER_ID, TOPIC_ID) is None


def test_a_corrupt_stored_parse_is_treated_as_absent(
    connection: sqlite3.Connection, tmp_path: Path, stored_pdf: Path
) -> None:
    parsing = service(connection, tmp_path)
    parsing.parse(PAPER_ID, TOPIC_ID)
    store = LocalArtifactStore(tmp_path / "artifacts")
    store.write_text(TOPIC_ID, "parsed", f"{PAPER_ID}.json", "{not json")

    assert parsing.load(PAPER_ID, TOPIC_ID) is None
