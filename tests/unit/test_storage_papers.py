import sqlite3
from datetime import UTC, date, datetime

from conftest import TOPIC_ID, candidate

from research_agent.domain.papers import SourceReference
from research_agent.storage.papers import SqlitePaperRepository


def _repository(connection: sqlite3.Connection) -> SqlitePaperRepository:
    return SqlitePaperRepository(connection)


def test_upsert_returns_the_canonical_id(connection: sqlite3.Connection) -> None:
    paper_id = _repository(connection).upsert(candidate(doi="https://doi.org/10.1234/abcd"))

    assert paper_id == "doi_10_1234_abcd"


def test_upsert_is_idempotent(connection: sqlite3.Connection) -> None:
    repository = _repository(connection)
    paper = candidate(doi="10.1234/abcd")

    first = repository.upsert(paper)
    second = repository.upsert(paper)

    assert first == second
    assert connection.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM paper_sources").fetchone()[0] == 1


def test_upsert_fills_previously_missing_metadata(connection: sqlite3.Connection) -> None:
    repository = _repository(connection)
    paper_id = repository.upsert(candidate(doi="10.1234/abcd", citation_count=3))
    repository.upsert(
        candidate(
            doi="10.1234/abcd",
            abstract="A late abstract.",
            venue="CoRL",
            publication_date=date(2026, 9, 1),
            citation_count=11,
        )
    )

    stored = repository.get(paper_id)

    assert stored is not None
    assert stored.abstract == "A late abstract."
    assert stored.venue == "CoRL"
    assert stored.publication_date == date(2026, 9, 1)
    assert stored.citation_count == 11


def test_upsert_accumulates_sources_without_duplicating(connection: sqlite3.Connection) -> None:
    repository = _repository(connection)
    paper_id = repository.upsert(candidate(doi="10.1234/abcd"))
    repository.upsert(
        candidate(
            doi="10.1234/abcd",
            sources=[
                SourceReference(source="arxiv", source_id="2409.00001"),
                SourceReference(source="openalex", source_id="W1", url="https://example.org/w1"),
            ],
        )
    )

    stored = repository.get(paper_id)

    assert stored is not None
    assert [source.source for source in stored.sources] == ["arxiv", "openalex"]
    assert stored.sources[1].url == "https://example.org/w1"


def test_get_round_trips_every_field(connection: sqlite3.Connection) -> None:
    repository = _repository(connection)
    paper = candidate(
        doi="10.1234/abcd",
        arxiv_id="2409.00001",
        abstract="Spatial reasoning for embodied agents.",
        authors=["Ada Lovelace", "Alan Turing"],
        publication_date=date(2026, 9, 1),
        venue="CoRL",
        citation_count=7,
    )
    paper_id = repository.upsert(paper)

    stored = repository.get(paper_id)

    assert stored is not None
    assert stored.canonical_id == paper_id
    assert stored.title == paper.title
    assert stored.abstract == paper.abstract
    assert stored.authors == ["Ada Lovelace", "Alan Turing"]
    assert stored.publication_date == date(2026, 9, 1)
    assert stored.discovered_at == datetime(2026, 9, 22, tzinfo=UTC)
    assert stored.doi == "10.1234/abcd"
    assert stored.arxiv_id == "2409.00001"
    assert stored.venue == "CoRL"
    assert stored.citation_count == 7


def test_get_returns_none_for_an_unknown_paper(connection: sqlite3.Connection) -> None:
    assert _repository(connection).get("doi_missing") is None


def test_seen_returns_only_known_ids(connection: sqlite3.Connection) -> None:
    repository = _repository(connection)
    paper_id = repository.upsert(candidate(doi="10.1234/abcd"))

    assert repository.seen([paper_id, "doi_missing"]) == {paper_id}
    assert repository.seen([]) == set()


def test_record_file_replaces_the_same_kind(connection: sqlite3.Connection) -> None:
    repository = _repository(connection)
    paper_id = repository.upsert(candidate(doi="10.1234/abcd"))
    connection.execute(
        "INSERT INTO runs (id, topic_id, started_at, status, active_classifier) "
        "VALUES ('r1', ?, '2026-09-22T00:00:00+00:00', 'running', 'A')",
        (TOPIC_ID,),
    )

    repository.record_file(paper_id, "pdf", "old.pdf", 10, "aaa", run_id="r1")
    repository.record_file(paper_id, "pdf", "new.pdf", 20, "bbb", run_id="r1")
    repository.record_file(paper_id, "parsed", "paper.md", 5, "ccc")

    assert repository.files_for(paper_id) == {"parsed": "paper.md", "pdf": "new.pdf"}
