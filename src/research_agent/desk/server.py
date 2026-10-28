"""Serve the reading desk on localhost.

The same process serves the static pages and the two JSON routes. Binding is loopback only:
a weekly run stays a separate command, and this process only reads the library and asks a model.
"""

import asyncio
import json
import logging
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse

import httpx
from pydantic import ConfigDict, Field, ValidationError

from research_agent.config import ApplicationSettings, StrictModel, TopicSettings
from research_agent.desk.ask import DeskLookupError, DeskReply, answer_question
from research_agent.desk.shelf import build_shelf, screened_papers
from research_agent.models.base import ModelProviderError
from research_agent.models.router import build_router
from research_agent.operations.health import HealthCheck, run_checks
from research_agent.operations.locks import RunLocked, run_lock
from research_agent.operations.runner import execute_run
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.database import apply_migrations, connect
from research_agent.storage.papers import SqlitePaperRepository
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
_HEALTH_TIMEOUT_SECONDS = 30.0
_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
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


class TopicSuggestRequest(StrictModel):
    """The name and optional description the desk page posts for keyword suggestions."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class DeskBackend(Protocol):
    """What the HTTP handler needs from the library. Tests substitute this."""

    def shelf(self) -> dict[str, object]: ...

    async def ask(self, request: AskRequest) -> DeskReply: ...

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


class LocalDesk:
    """Read the SQLite library and answer with the configured model router."""

    def __init__(self, database: Path, settings: ApplicationSettings) -> None:
        self._database = database
        self._settings = settings
        self._store = LocalArtifactStore(settings.data_directory)

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
            )
        finally:
            connection.close()

    async def ask(self, request: AskRequest) -> DeskReply:
        shelf = self.shelf()
        timeout = self._settings.models.nim.timeout_seconds
        async with httpx.AsyncClient(timeout=timeout) as client:
            router = build_router(client, self._settings)
            return await answer_question(
                router,
                shelf,
                topic_id=request.topic_id,
                run_id=request.run_id,
                question=request.question.strip(),
                paper_id=request.paper_id,
                max_chars=self._settings.reports.max_input_chars,
            )

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
            return screened_papers(
                run_id,
                SqliteResultRepository(connection),
                SqlitePaperRepository(connection),
                SqliteSelectionRepository(connection),
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
        """Clear one week's run. Deduplicated papers and their files are untouched."""
        connection = connect(self._database)
        try:
            SqliteRunRepository(connection).delete(run_id)
        finally:
            connection.close()

    def clear_topic(self, topic_id: str) -> int:
        """Clear every run a topic has, keeping the topic definition. Returns the count cleared."""
        connection = connect(self._database)
        try:
            return SqliteRunRepository(connection).delete_for_topic(topic_id)
        finally:
            connection.close()


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
            if len(segments) == 4 and segments[:2] == ["api", "papers"] and segments[3] == "pdf":
                pdf = backend.pdf_path(segments[2])
                if pdf is None:
                    self._json(404, {"error": "No stored PDF for this paper."})
                else:
                    self._bytes(200, "application/pdf", pdf.read_bytes())
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
            except ModelProviderError:
                _LOGGER.warning(
                    "desk answer failed",
                    extra={"node_name": "desk_ask", "status": "failed"},
                )
                self._json(502, {"error": "The model did not answer."})
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
            if len(segments) == 3 and segments[:2] == ["api", "runs"]:
                backend.delete_run(unquote(segments[2]))
                self._json(200, {"status": "cleared"})
            elif (
                len(segments) == 4
                and segments[0] == "api"
                and segments[1] == "topics"
                and segments[3] == "runs"
            ):
                cleared = backend.clear_topic(unquote(segments[2]))
                self._json(200, {"status": "cleared", "runs": cleared})
            elif (topic_id := _topic_route(path)) is not None:
                self._topic_action(lambda: backend.delete_topic(topic_id), 200, "deleted")
            else:
                self._json(404, {"error": "Not found."})

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

        def _bytes(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

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


def _reply_body(reply: DeskReply) -> dict[str, object]:
    return {
        "paragraphs": reply.paragraphs,
        "cites": reply.cites,
        "provider": reply.provider,
        "model": reply.model,
        "fellBack": reply.fell_back,
        "note": reply.note,
    }
