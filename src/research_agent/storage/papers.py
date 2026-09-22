"""Paper, source, and file persistence behind repository interfaces."""

import json
import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from typing import Literal, Protocol

from research_agent.discovery.normalize import canonical_id, normalize_candidate
from research_agent.domain.papers import PaperCandidate, SourceReference
from research_agent.storage.database import now_iso

FileKind = Literal["pdf", "parsed", "analysis", "report", "run_summary"]

_PAPER_COLUMNS = (
    "id, title, abstract, doi, arxiv_id, publication_date, venue, citation_count, "
    "authors_json, first_seen_at"
)


class PaperRepository(Protocol):
    """Storage-neutral paper repository."""

    def upsert(self, candidate: PaperCandidate) -> str: ...

    def get(self, paper_id: str) -> PaperCandidate | None: ...

    def seen(self, paper_ids: Iterable[str]) -> set[str]: ...

    def record_file(
        self,
        paper_id: str,
        kind: FileKind,
        path: str,
        byte_size: int,
        sha256: str,
        run_id: str | None = None,
    ) -> None: ...

    def files_for(self, paper_id: str) -> dict[str, str]: ...


class SqlitePaperRepository:
    """SQLite-backed :class:`PaperRepository` with idempotent upserts."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert(self, candidate: PaperCandidate) -> str:
        """Insert or refresh a paper and its sources; re-running only moves ``last_seen_at``."""
        paper = normalize_candidate(candidate)
        paper_id = paper.canonical_id or canonical_id(paper)
        timestamp = now_iso()
        values = {
            "id": paper_id,
            "title": paper.title,
            "abstract": paper.abstract,
            "doi": paper.doi,
            "arxiv_id": paper.arxiv_id,
            "publication_date": paper.publication_date.isoformat()
            if paper.publication_date
            else None,
            "venue": paper.venue,
            "citation_count": paper.citation_count,
            "authors_json": json.dumps(paper.authors),
            "first_seen_at": paper.discovered_at.isoformat(),
            "last_seen_at": timestamp,
        }
        with self._connection:
            self._connection.execute(
                f"INSERT INTO papers ({', '.join(values)}) "
                f"VALUES ({', '.join(f':{column}' for column in values)}) "
                "ON CONFLICT(id) DO UPDATE SET "
                "   title = excluded.title,"
                "   abstract = COALESCE(papers.abstract, excluded.abstract),"
                "   doi = COALESCE(papers.doi, excluded.doi),"
                "   arxiv_id = COALESCE(papers.arxiv_id, excluded.arxiv_id),"
                "   publication_date = COALESCE(papers.publication_date,"
                "       excluded.publication_date),"
                "   venue = COALESCE(papers.venue, excluded.venue),"
                "   citation_count = COALESCE("
                "       MAX(papers.citation_count, excluded.citation_count),"
                "       papers.citation_count, excluded.citation_count),"
                "   authors_json = excluded.authors_json,"
                "   last_seen_at = excluded.last_seen_at",
                values,
            )
            self._connection.executemany(
                "INSERT INTO paper_sources (paper_id, source, source_id, url, pdf_url) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(paper_id, source, source_id) DO UPDATE SET "
                "   url = COALESCE(paper_sources.url, excluded.url),"
                "   pdf_url = COALESCE(paper_sources.pdf_url, excluded.pdf_url)",
                [
                    (paper_id, source.source, source.source_id, source.url, source.pdf_url)
                    for source in paper.sources
                ],
            )
        return paper_id

    def get(self, paper_id: str) -> PaperCandidate | None:
        row = self._connection.execute(
            f"SELECT {_PAPER_COLUMNS} FROM papers WHERE id = ?", (paper_id,)
        ).fetchone()
        if row is None:
            return None
        sources = self._connection.execute(
            "SELECT source, source_id, url, pdf_url FROM paper_sources "
            "WHERE paper_id = ? ORDER BY source, source_id",
            (paper_id,),
        ).fetchall()
        published = row["publication_date"]
        return PaperCandidate(
            canonical_id=row["id"],
            title=row["title"],
            abstract=row["abstract"],
            authors=json.loads(row["authors_json"]),
            publication_date=date.fromisoformat(published) if published else None,
            discovered_at=datetime.fromisoformat(row["first_seen_at"]),
            sources=[SourceReference.model_validate(dict(source)) for source in sources],
            doi=row["doi"],
            arxiv_id=row["arxiv_id"],
            venue=row["venue"],
            citation_count=row["citation_count"],
        )

    def seen(self, paper_ids: Iterable[str]) -> set[str]:
        """Return the subset of ids already stored, so unchanged papers can reuse their work."""
        wanted = list(paper_ids)
        if not wanted:
            return set()
        placeholders = ", ".join("?" * len(wanted))
        rows = self._connection.execute(
            f"SELECT id FROM papers WHERE id IN ({placeholders})", wanted
        ).fetchall()
        return {row["id"] for row in rows}

    def record_file(
        self,
        paper_id: str,
        kind: FileKind,
        path: str,
        byte_size: int,
        sha256: str,
        run_id: str | None = None,
    ) -> None:
        """Record one stored artifact, replacing any earlier file of the same kind."""
        with self._connection:
            self._connection.execute(
                "INSERT INTO paper_files "
                "   (id, paper_id, run_id, kind, path, byte_size, sha256, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(paper_id, kind) DO UPDATE SET "
                "   run_id = excluded.run_id, path = excluded.path,"
                "   byte_size = excluded.byte_size, sha256 = excluded.sha256,"
                "   created_at = excluded.created_at",
                (f"{paper_id}:{kind}", paper_id, run_id, kind, path, byte_size, sha256, now_iso()),
            )

    def files_for(self, paper_id: str) -> dict[str, str]:
        rows = self._connection.execute(
            "SELECT kind, path FROM paper_files WHERE paper_id = ? ORDER BY kind", (paper_id,)
        ).fetchall()
        return {row["kind"]: row["path"] for row in rows}
