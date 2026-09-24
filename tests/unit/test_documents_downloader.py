import asyncio
import hashlib
import sqlite3
from pathlib import Path

import httpx
import pytest

from research_agent.config import DocumentSettings
from research_agent.documents.downloader import PdfDownloader
from research_agent.domain.papers import PaperCandidate, SourceReference
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.papers import SqlitePaperRepository
from tests.unit.conftest import TOPIC_ID, candidate

PDF = b"%PDF-1.7\n" + b"x" * 100


def paper(url: str | None = "https://example.org/a.pdf", **overrides: object) -> PaperCandidate:
    payload: dict[str, object] = {
        "canonical_id": "doi_10_1234_abcd",
        "doi": "10.1234/abcd",
        "sources": [
            SourceReference.model_validate(
                {"source": "openalex", "source_id": "W1", "pdf_url": url}
            )
        ],
    }
    payload.update(overrides)
    return candidate(**payload)


def downloader(
    connection: sqlite3.Connection,
    tmp_path: Path,
    handler: object,
    settings: DocumentSettings | None = None,
    retries: int = 2,
) -> PdfDownloader:
    return PdfDownloader(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
        LocalArtifactStore(tmp_path),
        SqlitePaperRepository(connection),
        settings,
        retries=retries,
    )


def serving(*responses: httpx.Response) -> tuple[object, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    remaining = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return remaining.pop(0) if remaining else httpx.Response(404)

    return handler, seen


def test_a_valid_pdf_is_stored_hashed_and_recorded(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    handler, seen = serving(
        httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})
    )
    repository = SqlitePaperRepository(connection)
    repository.upsert(paper())

    outcome = asyncio.run(downloader(connection, tmp_path, handler).acquire(paper(), TOPIC_ID))

    assert outcome.status == "stored"
    assert outcome.sha256 == hashlib.sha256(PDF).hexdigest()
    assert outcome.byte_size == len(PDF)
    assert outcome.path is not None and outcome.path.endswith("doi_10_1234_abcd.pdf")
    assert Path(outcome.path).read_bytes() == PDF
    assert repository.files_for("doi_10_1234_abcd")["pdf"] == outcome.path
    assert len(seen) == 1


def test_an_octet_stream_with_a_pdf_signature_is_accepted(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    handler, _ = serving(
        httpx.Response(200, content=PDF, headers={"content-type": "application/octet-stream"})
    )
    SqlitePaperRepository(connection).upsert(paper())

    outcome = asyncio.run(downloader(connection, tmp_path, handler).acquire(paper(), TOPIC_ID))

    assert outcome.status == "stored"


def test_html_masquerading_as_a_pdf_is_rejected_without_writing(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    handler, _ = serving(
        httpx.Response(
            200, content=b"<html>login</html>", headers={"content-type": "application/pdf"}
        )
    )

    outcome = asyncio.run(downloader(connection, tmp_path, handler).acquire(paper(), TOPIC_ID))

    assert outcome.status == "failed"
    assert outcome.reason is not None and "not a PDF" in outcome.reason
    assert not list(tmp_path.rglob("*.pdf"))


def test_an_html_content_type_is_refused_outright(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    handler, _ = serving(httpx.Response(200, content=PDF, headers={"content-type": "text/html"}))

    outcome = asyncio.run(downloader(connection, tmp_path, handler).acquire(paper(), TOPIC_ID))

    assert outcome.status == "failed"
    assert outcome.reason is not None and "unexpected content type" in outcome.reason


def test_an_oversize_response_is_abandoned(connection: sqlite3.Connection, tmp_path: Path) -> None:
    handler, _ = serving(
        httpx.Response(
            200, content=b"%PDF-" + b"x" * 5000, headers={"content-type": "application/pdf"}
        )
    )

    outcome = asyncio.run(
        downloader(connection, tmp_path, handler, DocumentSettings(max_pdf_bytes=1000)).acquire(
            paper(), TOPIC_ID
        )
    )

    assert outcome.status == "failed"
    assert outcome.reason is not None and "larger than 1000 bytes" in outcome.reason
    assert not list(tmp_path.rglob("*.pdf"))


def test_a_redirect_is_followed(connection: sqlite3.Connection, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a.pdf":
            return httpx.Response(302, headers={"location": "https://example.org/real.pdf"})
        return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})

    SqlitePaperRepository(connection).upsert(paper())

    outcome = asyncio.run(downloader(connection, tmp_path, handler).acquire(paper(), TOPIC_ID))

    assert outcome.status == "stored"


def test_a_missing_first_candidate_falls_through_to_the_second(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "arxiv.org" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})

    subject = paper(arxiv_id="2409.00001")
    SqlitePaperRepository(connection).upsert(subject)

    outcome = asyncio.run(downloader(connection, tmp_path, handler).acquire(subject, TOPIC_ID))

    assert outcome.status == "stored"
    assert outcome.url == "https://example.org/a.pdf"


def test_a_transient_failure_is_retried_to_the_ceiling(
    connection: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    handler, seen = serving(*(httpx.Response(503) for _ in range(3)))

    outcome = asyncio.run(
        downloader(connection, tmp_path, handler, retries=2).acquire(paper(), TOPIC_ID)
    )

    assert outcome.status == "failed"
    assert len(seen) == 3


def test_a_forbidden_response_is_not_retried(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    handler, seen = serving(httpx.Response(403))

    outcome = asyncio.run(downloader(connection, tmp_path, handler).acquire(paper(), TOPIC_ID))

    assert outcome.status == "failed"
    assert len(seen) == 1


def test_a_paper_with_no_url_is_unavailable_not_failed(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    handler, seen = serving()

    outcome = asyncio.run(downloader(connection, tmp_path, handler).acquire(paper(None), TOPIC_ID))

    assert outcome.status == "unavailable"
    assert seen == []


def test_an_already_stored_pdf_costs_no_request(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    LocalArtifactStore(tmp_path).write_bytes(TOPIC_ID, "papers", "doi_10_1234_abcd.pdf", PDF)
    handler, seen = serving()

    outcome = asyncio.run(downloader(connection, tmp_path, handler).acquire(paper(), TOPIC_ID))

    assert outcome.status == "cached"
    assert seen == []


def test_a_paper_without_a_canonical_id_is_reported_not_raised(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    handler, _ = serving()
    anonymous = candidate(canonical_id=None)

    outcome = asyncio.run(downloader(connection, tmp_path, handler).acquire(anonymous, TOPIC_ID))

    assert (outcome.status, outcome.paper_id) == ("failed", "unknown")


def test_one_failing_paper_does_not_affect_the_others(
    connection: sqlite3.Connection, tmp_path: Path
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "bad" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"})

    repository = SqlitePaperRepository(connection)
    good = paper()
    bad = paper("https://example.org/bad.pdf", canonical_id="doi_10_1234_efgh", doi="10.1234/efgh")
    repository.upsert(good)
    repository.upsert(bad)

    outcomes = asyncio.run(
        downloader(connection, tmp_path, handler).acquire_many([good, bad], TOPIC_ID)
    )

    assert [outcome.status for outcome in outcomes] == ["stored", "failed"]


async def _no_sleep(delay: float) -> None:
    return None
