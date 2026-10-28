"""Serve the reading desk on localhost.

The same process serves the static pages and the two JSON routes. Binding is loopback only:
a weekly run stays a separate command, and this process only reads the library and asks a model.
"""

import asyncio
import json
import logging
import shutil
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from pydantic import ConfigDict, Field, ValidationError

from research_agent.config import ApplicationSettings, StrictModel, TopicSettings
from research_agent.desk.ask import DeskLookupError, DeskReply, answer_question, failure_message
from research_agent.desk.settings_page import SettingsProblem, overrides_for
from research_agent.desk.settings_page import page as settings_page
from research_agent.desk.shelf import (
    build_run,
    build_shelf,
    owned_files,
    run_report,
    screened_papers,
)
from research_agent.exports.citations import to_bibtex, to_ris
from research_agent.models.base import ModelProviderError
from research_agent.models.router import build_router
from research_agent.operations.health import HealthCheck, run_checks
from research_agent.operations.locks import RunLocked, run_lock
from research_agent.operations.runner import execute_run
from research_agent.storage.app_settings import SqliteSettingsOverrides, load_settings
from research_agent.storage.artifacts import LocalArtifactStore, safe_name
from research_agent.storage.asks import AskTurn, SqliteAskRepository
from research_agent.storage.database import apply_migrations, connect
from research_agent.storage.feedback import SqliteFeedbackRepository
from research_agent.storage.library import SqliteLibraryRepository
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.reading import ReadingState, SqliteReadingRepository
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from research_agent.storage.selections import SqliteSelectionRepository
from research_agent.storage.topics import (
    SqliteTopicRepository,
    TopicNotFoundError,
    TopicStoreError,
)
from research_agent.topics.suggest import suggest_keywords

_LOGGER = logging.getLogger(__name__)
_MAX_BODY = 16_000
_LIBRARY_PAGE_MAX = 100
_ALL_RUNS = 1_000_000
_CITATION_TYPES = {
    "bib": "application/x-bibtex; charset=utf-8",
    "ris": "application/x-research-info-systems; charset=utf-8",
}
_HEALTH_TIMEOUT_SECONDS = 30.0
_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".png": "image/png",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}


class AskRequest(StrictModel):
    """The question the desk page posts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    question: str = Field(min_length=1, max_length=2000)
    topic_id: str = Field(min_length=1, alias="topicId")
    run_id: str = Field(min_length=1, alias="runId")
    paper_id: str | None = Field(default=None, alias="paperId")


class SettingsUpdate(StrictModel):
    """Every editable field the Settings page submits, by dotted path."""

    values: dict[str, str | int | float | list[str]]


class VoteRequest(StrictModel):
    """A relevance vote for one paper under one topic; 0 clears it."""

    model_config = ConfigDict(extra="forbid")

    vote: Literal[-1, 0, 1]


class ReadingUpdate(StrictModel):
    """A change to a paper's reading state; fields left out keep their stored value."""

    model_config = ConfigDict(extra="forbid")

    read: bool | None = None
    saved: bool | None = None
    note: str | None = None


class TopicSuggestRequest(StrictModel):
    """The name and optional description the desk page posts for keyword suggestions."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class DeskBackend(Protocol):
    """What the HTTP handler needs from the library. Tests substitute this."""

    def shelf(self) -> dict[str, object]: ...

    async def ask(self, request: AskRequest) -> DeskReply: ...

    def thread(self, run_id: str, paper_id: str | None) -> list[dict[str, object]]: ...

    def clear_thread(self, run_id: str, paper_id: str | None) -> int: ...

    async def suggest(self, request: TopicSuggestRequest) -> list[str]: ...

    def create_and_run(self, topic: TopicSettings) -> None: ...

    def delete_run(self, run_id: str) -> None: ...

    def clear_topic(self, topic_id: str) -> int: ...

    def update_topic(self, topic: TopicSettings) -> None: ...

    def delete_topic(self, topic_id: str) -> None: ...

    def run_topic(self, topic_id: str) -> None: ...

    async def health(self) -> list[HealthCheck]: ...

    def screened(self, run_id: str) -> list[dict[str, object]]: ...

    def pdf_path(self, paper_id: str) -> Path | None: ...

    def update_reading(self, paper_id: str, update: ReadingUpdate) -> ReadingState: ...

    def set_vote(self, topic_id: str, paper_id: str, vote: Literal[-1, 0, 1]) -> None: ...

    def report(self, run_id: str) -> tuple[str, str] | None: ...

    def citations(self, run_id: str | None, fmt: str) -> tuple[str, str] | None: ...

    def run(self, run_id: str) -> dict[str, object] | None: ...

    def storage(self) -> dict[str, object]: ...

    def settings_page(self) -> dict[str, object]: ...

    def save_settings(self, values: dict[str, object] | None) -> dict[str, object]: ...

    def library(self, query: "LibraryQuery") -> dict[str, object]: ...


class LibraryQuery(StrictModel):
    """What the library page asks for: a filter and a page."""

    topic: str | None = None
    show: Literal["all", "unread", "saved"] = "all"
    q: str = Field(default="", max_length=200)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=25, ge=1, le=_LIBRARY_PAGE_MAX)


class LocalDesk:
    """Read the SQLite library and answer with the configured model router."""

    def __init__(
        self, database: Path, settings: ApplicationSettings, settings_file: Path | None = None
    ) -> None:
        self._database = database
        self._settings = settings
        self._settings_file = settings_file
        self._store = LocalArtifactStore(settings.data_directory)

    def settings_page(self) -> dict[str, object]:
        connection = connect(self._database)
        try:
            overrides = SqliteSettingsOverrides(connection).get()
        finally:
            connection.close()
        return settings_page(self._settings, self._settings_file, overrides)

    def save_settings(self, values: dict[str, object] | None) -> dict[str, object]:
        """Save the page's values (None resets to the file), then use them from the next call on.

        A run already going keeps the settings it started with.
        """
        if self._settings_file is None:
            raise SettingsProblem("This desk was started without a settings file.")
        changes = {} if values is None else overrides_for(values, self._settings_file)
        connection = connect(self._database)
        try:
            SqliteSettingsOverrides(connection).save(changes)
        finally:
            connection.close()
        self._settings = load_settings(self._settings_file)
        return self.settings_page()

    def shelf(self) -> dict[str, object]:
        connection = connect(self._database)
        try:
            # Read per request: topics created from the desk must appear without a restart.
            return build_shelf(
                SqliteTopicRepository(connection).list(),
                SqliteRunRepository(connection),
                SqliteResultRepository(connection),
                SqlitePaperRepository(connection),
                SqliteSelectionRepository(connection),
                self._store,
                reading=SqliteReadingRepository(connection),
                feedback=SqliteFeedbackRepository(connection),
            )
        finally:
            connection.close()

    async def ask(self, request: AskRequest) -> DeskReply:
        """Answer with the thread's earlier turns as context, then add this turn to it."""
        shelf = self.shelf()
        question = request.question.strip()
        connection = connect(self._database)
        try:
            asks = SqliteAskRepository(connection)
            earlier = asks.turns(request.run_id, request.paper_id)
            timeout = self._settings.models.nim.timeout_seconds
            async with httpx.AsyncClient(timeout=timeout) as client:
                router = build_router(client, self._settings)
                reply = await answer_question(
                    router,
                    shelf,
                    topic_id=request.topic_id,
                    run_id=request.run_id,
                    question=question,
                    paper_id=request.paper_id,
                    max_chars=self._settings.reports.max_input_chars,
                    history=[(turn.question, turn.paragraphs) for turn in earlier],
                )
            asks.add(
                request.run_id,
                request.paper_id,
                AskTurn(
                    question=question,
                    paragraphs=reply.paragraphs,
                    cites=reply.cites,
                    note=reply.note,
                ),
            )
        finally:
            connection.close()
        return reply

    def thread(self, run_id: str, paper_id: str | None) -> list[dict[str, object]]:
        connection = connect(self._database)
        try:
            turns = SqliteAskRepository(connection).turns(run_id, paper_id)
        finally:
            connection.close()
        return [
            turn.model_dump(include={"question", "paragraphs", "cites", "note"}) for turn in turns
        ]

    def clear_thread(self, run_id: str, paper_id: str | None) -> int:
        connection = connect(self._database)
        try:
            return SqliteAskRepository(connection).clear(run_id, paper_id)
        finally:
            connection.close()

    async def suggest(self, request: TopicSuggestRequest) -> list[str]:
        timeout = self._settings.models.local.timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            router = build_router(client, self._settings)
            return await suggest_keywords(router, request.name, request.description)

    def create_and_run(self, topic: TopicSettings) -> None:
        """Store the topic, then start its first run in the background."""
        connection = connect(self._database)
        try:
            apply_migrations(connection)
            SqliteTopicRepository(connection).add(topic)
        finally:
            connection.close()
        self._start_run(topic)

    def update_topic(self, topic: TopicSettings) -> None:
        connection = connect(self._database)
        try:
            SqliteTopicRepository(connection).update(topic)
        finally:
            connection.close()

    def delete_topic(self, topic_id: str) -> None:
        """Delete a topic and its runs; refused while its run holds the lock."""
        connection = connect(self._database)
        try:
            with run_lock(self._settings.data_directory, topic_id):
                SqliteTopicRepository(connection).delete(topic_id)
        finally:
            connection.close()

    def run_topic(self, topic_id: str) -> None:
        """Start a stored topic's run in the background, unless it is disabled or running."""
        connection = connect(self._database)
        try:
            topic = SqliteTopicRepository(connection).get(topic_id)
            running = any(
                record.topic_id == topic_id
                for record in SqliteRunRepository(connection).open_runs()
            )
        finally:
            connection.close()
        if topic is None:
            raise TopicNotFoundError(f"unknown topic: {topic_id}")
        if not topic.enabled:
            raise TopicStoreError(f"{topic.name} is disabled; enable it to run it.")
        if running:
            raise RunLocked(f"{topic.name} is already running.")
        self._start_run(topic)

    def citations(self, run_id: str | None, fmt: str) -> tuple[str, str] | None:
        """A run's kept papers, or every saved paper when no run is named, as (name, text)."""
        connection = connect(self._database)
        try:
            papers = SqlitePaperRepository(connection)
            if run_id is None:
                ids, stem = SqliteReadingRepository(connection).saved_ids(), "saved_papers"
            else:
                run = SqliteRunRepository(connection).get(run_id)
                if run is None:
                    return None
                ids = SqliteSelectionRepository(connection).selected_for(run_id)
                stem = f"{run.topic_id}_{run.started_at.date().isoformat()}_papers"
            found = [paper for paper in (papers.get(paper_id) for paper_id in ids) if paper]
        finally:
            connection.close()
        text = to_bibtex(found) if fmt == "bib" else to_ris(found)
        return f"{stem}.{fmt}", text

    def run(self, run_id: str) -> dict[str, object] | None:
        connection = connect(self._database)
        try:
            runs = SqliteRunRepository(connection)
            record = runs.get(run_id)
            topic = SqliteTopicRepository(connection).get(record.topic_id) if record else None
            if record is None or topic is None:
                return None
            return build_run(
                topic,
                record,
                runs,
                SqliteResultRepository(connection),
                SqlitePaperRepository(connection),
                SqliteSelectionRepository(connection),
                self._store,
                reading=SqliteReadingRepository(connection),
                feedback=SqliteFeedbackRepository(connection),
            )
        finally:
            connection.close()

    def library(self, query: "LibraryQuery") -> dict[str, object]:
        """A page of every paper ever kept, newest run first, with its reading state."""
        connection = connect(self._database)
        try:
            total, entries = SqliteLibraryRepository(connection).page(
                topic_id=query.topic,
                unread_only=query.show == "unread",
                saved_only=query.show == "saved",
                search=query.q,
                offset=query.offset,
                limit=query.limit,
            )
            papers = SqlitePaperRepository(connection)
            states = SqliteReadingRepository(connection).states_for(e.paper_id for e in entries)
            rows: list[dict[str, object]] = []
            for entry in entries:
                paper = papers.get(entry.paper_id)
                if paper is None:
                    continue
                state = states.get(entry.paper_id, ReadingState())
                rows.append(
                    {
                        "id": entry.paper_id,
                        "title": paper.title,
                        "authors": list(paper.authors),
                        "venue": paper.venue,
                        "date": paper.publication_date.isoformat()
                        if paper.publication_date
                        else None,
                        "topicId": entry.topic_id,
                        "topicName": entry.topic_name,
                        "runId": entry.run_id,
                        "runDate": entry.run_started_at.date().isoformat(),
                        "action": entry.action,
                        "reading": state.model_dump(),
                    }
                )
        finally:
            connection.close()
        return {"total": total, "offset": query.offset, "limit": query.limit, "papers": rows}

    def report(self, run_id: str) -> tuple[str, str] | None:
        connection = connect(self._database)
        try:
            return run_report(
                run_id,
                SqliteRunRepository(connection),
                SqliteResultRepository(connection),
                self._store,
            )
        finally:
            connection.close()

    def set_vote(self, topic_id: str, paper_id: str, vote: Literal[-1, 0, 1]) -> None:
        """Record or clear the reader's relevance vote; future runs screen with it."""
        connection = connect(self._database)
        try:
            if SqliteTopicRepository(connection).get(topic_id) is None:
                raise DeskLookupError("That topic is not in the library.")
            if SqlitePaperRepository(connection).get(paper_id) is None:
                raise DeskLookupError("That paper is not in the library.")
            SqliteFeedbackRepository(connection).set_vote(topic_id, paper_id, vote or None)
        finally:
            connection.close()

    def update_reading(self, paper_id: str, update: ReadingUpdate) -> ReadingState:
        """Merge a change into a paper's reading state; an unknown paper is a lookup error."""
        connection = connect(self._database)
        try:
            if SqlitePaperRepository(connection).get(paper_id) is None:
                raise DeskLookupError("That paper is not in the library.")
            reading = SqliteReadingRepository(connection)
            current = reading.states_for([paper_id]).get(paper_id, ReadingState())
            state = ReadingState.model_validate(
                {**current.model_dump(), **update.model_dump(exclude_none=True)}
            )
            reading.save(paper_id, state)
            return state
        finally:
            connection.close()

    def pdf_path(self, paper_id: str) -> Path | None:
        """The stored PDF for a paper, only if it really is a PDF inside the library folder."""
        connection = connect(self._database)
        try:
            stored = SqlitePaperRepository(connection).files_for(paper_id).get("pdf")
        finally:
            connection.close()
        if stored is None:
            return None
        path = Path(stored).resolve()
        library = self._settings.data_directory.resolve()
        if path.suffix.lower() != ".pdf" or not path.is_relative_to(library) or not path.is_file():
            return None
        return path

    def screened(self, run_id: str) -> list[dict[str, object]]:
        connection = connect(self._database)
        try:
            run = SqliteRunRepository(connection).get(run_id)
            return screened_papers(
                run_id,
                SqliteResultRepository(connection),
                SqlitePaperRepository(connection),
                SqliteSelectionRepository(connection),
                topic_id=run.topic_id if run else "",
                feedback=SqliteFeedbackRepository(connection),
            )
        finally:
            connection.close()

    async def health(self) -> list[HealthCheck]:
        async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT_SECONDS) as client:
            return await run_checks(self._settings, client)

    def _start_run(self, topic: TopicSettings) -> None:
        """Run the pipeline on a daemon thread; a run takes minutes and must not block a request."""

        def _run() -> None:
            run_connection = connect(self._database)
            try:
                asyncio.run(execute_run(run_connection, self._settings, topic))
            except Exception:
                _LOGGER.exception(
                    "background pipeline run failed",
                    extra={"node_name": "topic_run", "status": "failed"},
                )
            finally:
                run_connection.close()

        threading.Thread(target=_run, daemon=True).start()

    def delete_run(self, run_id: str) -> None:
        """Clear one run and the files only it owns; refused while its topic is running.

        Its papers stay in the library, with their PDFs, parsed text and analyses.
        """
        connection = connect(self._database)
        try:
            record = SqliteRunRepository(connection).get(run_id)
            if record is not None:
                with self._idle(connection, record.topic_id):
                    self._clear(connection, record.topic_id, {run_id})
        finally:
            connection.close()

    def clear_topic(self, topic_id: str) -> int:
        """Clear every run a topic has, keeping the topic definition. Returns the count cleared."""
        connection = connect(self._database)
        try:
            with self._idle(connection, topic_id):
                return self._clear(connection, topic_id, None)
        finally:
            connection.close()

    @contextmanager
    def _idle(self, connection: sqlite3.Connection, topic_id: str) -> Iterator[None]:
        """Hold the topic's run lock, so nothing is cleared out from under a running run."""
        try:
            with run_lock(self._settings.data_directory, topic_id):
                yield
        except RunLocked as error:
            topic = SqliteTopicRepository(connection).get(topic_id)
            name = topic.name if topic else topic_id
            raise RunLocked(f"{name} is running; clear runs after it finishes.") from error

    def _clear(self, connection: sqlite3.Connection, topic_id: str, ids: set[str] | None) -> int:
        """Delete runs (all of the topic's when `ids` is None), then the files they alone own."""
        runs = SqliteRunRepository(connection)
        every = runs.recent(topic_id, _ALL_RUNS)
        cleared = [record for record in every if ids is None or record.id in ids]
        staying = [record for record in every if record not in cleared]
        files = owned_files(cleared, staying, SqliteResultRepository(connection), self._store)
        for record in cleared:
            runs.delete(record.id)
        for owner, kind, name in files:
            self._store.delete(owner, kind, name)
        return len(cleared)

    def storage(self) -> dict[str, object]:
        """Bytes on disk per topic folder and for the database, and what the disk has free."""
        root = self._settings.data_directory
        connection = connect(self._database)
        try:
            topic_ids = [topic.id for topic in SqliteTopicRepository(connection).list()]
        finally:
            connection.close()
        return {
            "topics": {
                topic_id: _folder_bytes(root / "topics" / safe_name(topic_id))
                for topic_id in topic_ids
            },
            "database": sum(path.stat().st_size for path in root.glob(f"{self._database.name}*")),
            "free": shutil.disk_usage(root).free,
        }


def serve(backend: DeskBackend, web_root: Path, port: int) -> None:
    """Block until the process is interrupted. The socket listens on 127.0.0.1 only."""
    handler = _handler(backend, web_root.resolve())
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    _LOGGER.info("desk listening", extra={"status": f"127.0.0.1:{port}"})
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _handler(backend: DeskBackend, web_root: Path) -> type[BaseHTTPRequestHandler]:
    class DeskHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            if self._foreign():
                return
            path = urlparse(self.path).path
            if path == "/api/shelf":
                self._json(200, backend.shelf())
                return
            segments = [unquote(segment) for segment in path.split("/") if segment]
            if len(segments) == 4 and segments[:2] == ["api", "runs"] and segments[3] == "screened":
                self._json(200, {"papers": backend.screened(segments[2])})
                return
            if path == "/api/library":
                raw = {
                    key: values[0] for key, values in parse_qs(urlparse(self.path).query).items()
                }
                try:
                    query = LibraryQuery.model_validate(raw)
                except ValidationError as error:
                    self._json(400, {"error": _first_problem(error)})
                    return
                self._json(200, backend.library(query))
                return
            if len(segments) == 3 and segments[:2] == ["api", "runs"]:
                run = backend.run(segments[2])
                if run is None:
                    self._json(404, {"error": "That run is not in the library."})
                else:
                    self._json(200, run)
                return
            run_citations = (
                len(segments) == 4
                and segments[:2] == ["api", "runs"]
                and segments[3] == "citations"
            )
            if run_citations or segments == ["api", "saved", "citations"]:
                citation_run = segments[2] if run_citations else None
                fmt = parse_qs(urlparse(self.path).query).get("format", ["bib"])[0]
                if fmt not in _CITATION_TYPES:
                    self._json(400, {"error": "Choose format=bib or format=ris."})
                    return
                export = backend.citations(citation_run, fmt)
                if export is None:
                    self._json(404, {"error": "That run is not in the library."})
                    return
                name, text = export
                self._bytes(
                    200,
                    _CITATION_TYPES[fmt],
                    text.encode("utf-8"),
                    {"Content-Disposition": f'attachment; filename="{name}"'},
                )
                return
            if len(segments) == 4 and segments[:2] == ["api", "runs"] and segments[3] == "report":
                report = backend.report(segments[2])
                if report is None:
                    self._json(404, {"error": "No report was written for this run."})
                else:
                    name, text = report
                    self._bytes(
                        200,
                        "text/markdown; charset=utf-8",
                        text.encode("utf-8"),
                        {"Content-Disposition": f'attachment; filename="{name}"'},
                    )
                return
            if len(segments) == 4 and segments[:2] == ["api", "papers"] and segments[3] == "pdf":
                pdf = backend.pdf_path(segments[2])
                if pdf is None:
                    self._json(404, {"error": "No stored PDF for this paper."})
                else:
                    self._bytes(200, "application/pdf", pdf.read_bytes())
                return
            if (thread_route := _ask_route(self.path)) is not None:
                self._json(200, {"turns": backend.thread(*thread_route)})
                return
            if path == "/api/settings":
                self._json(200, backend.settings_page())
                return
            if path == "/api/storage":
                self._json(200, backend.storage())
                return
            if path == "/api/health":
                checks = asyncio.run(backend.health())
                self._json(200, {"checks": [check.model_dump() for check in checks]})
                return
            self._file(path)

        def do_POST(self) -> None:
            if self._foreign():
                return
            path = urlparse(self.path).path
            if path == "/api/ask":
                self._ask()
            elif path == "/api/topics/suggest":
                self._suggest_topic()
            elif path == "/api/topics":
                self._create_topic()
            elif (topic_id := _topic_route(path, "run")) is not None:
                self._discard_body()
                self._topic_action(lambda: backend.run_topic(topic_id), 202, "started")
            else:
                self._json(404, {"error": "Not found."})

        def do_PUT(self) -> None:
            if self._foreign():
                return
            segments = [unquote(part) for part in urlparse(self.path).path.split("/") if part]
            if segments == ["api", "settings"]:
                try:
                    update = SettingsUpdate.model_validate(_read_json(self))
                except (ValueError, ValidationError):
                    self._json(400, {"error": "The settings could not be read."})
                    return
                self._save_settings(dict(update.values))
                return
            if (
                len(segments) == 4
                and segments[:2] == ["api", "papers"]
                and segments[3] == "reading"
            ):
                self._update_reading(segments[2])
                return
            if (
                len(segments) == 5
                and segments[:2] == ["api", "topics"]
                and segments[3] == "feedback"
            ):
                self._set_vote(segments[2], segments[4])
                return
            topic_id = _topic_route(urlparse(self.path).path)
            if topic_id is None:
                self._json(404, {"error": "Not found."})
                return
            try:
                payload = _read_json(self)
                if not isinstance(payload, dict):
                    raise ValueError("body")
                topic = TopicSettings.model_validate({**payload, "id": topic_id})
            except ValidationError as error:
                self._json(400, {"error": _first_problem(error)})
                return
            except ValueError:
                self._json(400, {"error": "The topic could not be read."})
                return
            self._topic_action(lambda: backend.update_topic(topic), 200, "updated")

        def _set_vote(self, topic_id: str, paper_id: str) -> None:
            try:
                request = VoteRequest.model_validate(_read_json(self))
                backend.set_vote(topic_id, paper_id, request.vote)
            except ValidationError as error:
                self._json(400, {"error": _first_problem(error)})
                return
            except ValueError:
                self._json(400, {"error": "The vote could not be read."})
                return
            except DeskLookupError as error:
                self._json(404, {"error": str(error)})
                return
            self._json(200, {"vote": request.vote})

        def _update_reading(self, paper_id: str) -> None:
            try:
                update = ReadingUpdate.model_validate(_read_json(self))
                state = backend.update_reading(paper_id, update)
            except ValidationError as error:
                self._json(400, {"error": _first_problem(error)})
                return
            except ValueError:
                self._json(400, {"error": "The change could not be read."})
                return
            except DeskLookupError as error:
                self._json(404, {"error": str(error)})
                return
            self._json(200, state.model_dump())

        def _topic_action(self, action: Callable[[], None], status: int, done: str) -> None:
            """Run a topic change, mapping a missing topic to 404 and a conflict to 409."""
            try:
                action()
            except TopicNotFoundError as error:
                self._json(404, {"error": str(error)})
            except (TopicStoreError, RunLocked) as error:
                self._json(409, {"error": str(error)})
            else:
                self._json(status, {"status": done})

        def _ask(self) -> None:
            try:
                payload = _read_json(self)
                request = AskRequest.model_validate(payload)
            except (ValueError, ValidationError):
                self._json(400, {"error": "The question could not be read."})
                return
            try:
                reply = asyncio.run(backend.ask(request))
            except DeskLookupError as error:
                self._json(404, {"error": str(error)})
                return
            except ModelProviderError as error:
                _LOGGER.warning(
                    "desk answer failed: %s",
                    error,
                    extra={
                        "node_name": "desk_ask",
                        "status": "failed",
                        "error_type": error.category,
                    },
                )
                self._json(502, {"error": failure_message(error), "setup": True})
                return
            self._json(200, _reply_body(reply))

        def _suggest_topic(self) -> None:
            try:
                payload = _read_json(self)
                request = TopicSuggestRequest.model_validate(payload)
            except (ValueError, ValidationError):
                self._json(400, {"error": "The topic name could not be read."})
                return
            try:
                keywords = asyncio.run(backend.suggest(request))
            except ModelProviderError:
                _LOGGER.warning(
                    "keyword suggestion failed",
                    extra={"node_name": "topic_keywords", "status": "failed"},
                )
                self._json(502, {"error": "The model did not answer."})
                return
            self._json(200, {"keywords": keywords})

        def _create_topic(self) -> None:
            try:
                payload = _read_json(self)
                topic = TopicSettings.model_validate(payload)
            except ValidationError as error:
                self._json(400, {"error": _first_problem(error)})
                return
            except ValueError:
                self._json(400, {"error": "The topic could not be read."})
                return
            try:
                backend.create_and_run(topic)
            except TopicStoreError as error:
                self._json(409, {"error": str(error)})
                return
            self._json(202, {"status": "started", "topicId": topic.id})

        def do_DELETE(self) -> None:
            if self._foreign():
                return
            self._discard_body()
            path = urlparse(self.path).path
            segments = [segment for segment in path.split("/") if segment]
            if path == "/api/settings":
                self._save_settings(None)
            elif (thread_route := _ask_route(self.path)) is not None:
                cleared = backend.clear_thread(*thread_route)
                self._json(200, {"status": "cleared", "turns": cleared})
            elif len(segments) == 3 and segments[:2] == ["api", "runs"]:
                run_id = unquote(segments[2])
                self._topic_action(lambda: backend.delete_run(run_id), 200, "cleared")
            elif (
                len(segments) == 4
                and segments[0] == "api"
                and segments[1] == "topics"
                and segments[3] == "runs"
            ):
                try:
                    cleared = backend.clear_topic(unquote(segments[2]))
                except RunLocked as error:
                    self._json(409, {"error": str(error)})
                else:
                    self._json(200, {"status": "cleared", "runs": cleared})
            elif (topic_id := _topic_route(path)) is not None:
                self._topic_action(lambda: backend.delete_topic(topic_id), 200, "deleted")
            else:
                self._json(404, {"error": "Not found."})

        def _save_settings(self, values: dict[str, object] | None) -> None:
            try:
                self._json(200, backend.save_settings(values))
            except SettingsProblem as error:
                self._json(400 if values is not None else 409, {"error": str(error)})

        def _discard_body(self) -> None:
            """Consume a body no route reads; left unread, it would corrupt the next request."""
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = _MAX_BODY + 1
            if length > _MAX_BODY:
                self.close_connection = True
            elif length > 0:
                self.rfile.read(length)

        def _foreign(self) -> bool:
            """Refuse DNS rebinding (a foreign Host) and cross-site requests (a foreign Origin)."""
            port = self.connection.getsockname()[1]
            local = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            if self.headers.get("Host") in local and (
                origin is None or origin.removeprefix("http://") in local
            ):
                return False
            self._json(403, {"error": "Forbidden."})
            return True

        def log_message(self, format: str, *args: object) -> None:
            _LOGGER.info(
                "desk request",
                extra={"node_name": "desk", "status": self.path.split("?", 1)[0]},
            )

        def _file(self, path: str) -> None:
            relative = "index.html" if path in ("", "/") else path.lstrip("/")
            try:
                candidate = (web_root / unquote(relative)).resolve()
                candidate.relative_to(web_root)
            except ValueError:
                self._json(404, {"error": "Not found."})
                return
            if not candidate.is_file() or candidate.suffix.lower() not in _TYPES:
                self._json(404, {"error": "Not found."})
                return
            body = candidate.read_bytes()
            self._bytes(200, _TYPES[candidate.suffix.lower()], body)

        def _json(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode("utf-8")
            self._bytes(status, "application/json; charset=utf-8", body)

        def _bytes(
            self,
            status: int,
            content_type: str,
            body: bytes,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if self.close_connection:
                self.send_header("Connection", "close")
            try:
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # The browser left mid-reply (a reload, a closed tab): normal, not a server fault.
                self.close_connection = True
                _LOGGER.debug(
                    "client disconnected before the reply was sent",
                    extra={"node_name": "desk", "status": self.path.split("?", 1)[0]},
                )

    return DeskHandler


def _topic_route(path: str, action: str | None = None) -> str | None:
    """The topic id in /api/topics/<id>, or /api/topics/<id>/<action> when an action is given."""
    segments = [unquote(segment) for segment in path.split("/") if segment]
    if segments[:2] != ["api", "topics"] or len(segments) != (4 if action else 3):
        return None
    if action and segments[3] != action:
        return None
    return segments[2]


def _first_problem(error: ValidationError) -> str:
    """One readable line from a validation error, for the page to show beside the form."""
    problem = error.errors()[0]
    field = ".".join(str(part) for part in problem["loc"])
    message = str(problem["msg"]).removeprefix("Value error, ")
    return f"{field}: {message}" if field else message


def _read_json(handler: BaseHTTPRequestHandler) -> object:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > _MAX_BODY:
        # An oversized body stays unread, so this connection cannot carry another request.
        handler.close_connection = True
        raise ValueError("body length")
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("body") from error


def _folder_bytes(folder: Path) -> int:
    return sum(path.stat().st_size for path in folder.rglob("*") if path.is_file())


def _ask_route(raw_path: str) -> tuple[str, str | None] | None:
    """(run id, paper id or None) for /api/runs/<id>/ask[?paper=<id>], else None."""
    url = urlparse(raw_path)
    segments = [unquote(segment) for segment in url.path.split("/") if segment]
    if len(segments) != 4 or segments[:2] != ["api", "runs"] or segments[3] != "ask":
        return None
    paper = parse_qs(url.query).get("paper", [""])[0]
    return segments[2], paper or None


def _reply_body(reply: DeskReply) -> dict[str, object]:
    return {
        "paragraphs": reply.paragraphs,
        "cites": reply.cites,
        "provider": reply.provider,
        "model": reply.model,
        "fellBack": reply.fell_back,
        "note": reply.note,
    }
