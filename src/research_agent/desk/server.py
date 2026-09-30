"""Serve the reading desk on localhost.

The same process serves the static pages and the two JSON routes. Binding is loopback only:
a weekly run stays a separate command, and this process only reads the library and asks a model.
"""

import asyncio
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse

import httpx
from pydantic import ConfigDict, Field, ValidationError

from research_agent.config import ApplicationSettings, StrictModel, TopicSettings
from research_agent.desk.ask import DeskLookupError, DeskReply, answer_question
from research_agent.desk.shelf import build_shelf
from research_agent.models.base import ModelProviderError
from research_agent.models.router import build_router
from research_agent.storage.artifacts import LocalArtifactStore
from research_agent.storage.database import connect
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.results import SqliteResultRepository
from research_agent.storage.runs import SqliteRunRepository
from research_agent.storage.selections import SqliteSelectionRepository

_LOGGER = logging.getLogger(__name__)
_MAX_BODY = 16_000
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


class DeskBackend(Protocol):
    """What the HTTP handler needs from the library. Tests substitute this."""

    def shelf(self) -> dict[str, object]: ...

    async def ask(self, request: AskRequest) -> DeskReply: ...


class LocalDesk:
    """Read the SQLite library and answer with the configured model router."""

    def __init__(
        self,
        database: Path,
        settings: ApplicationSettings,
        topics: list[TopicSettings],
    ) -> None:
        self._database = database
        self._settings = settings
        self._topics = topics
        self._store = LocalArtifactStore(settings.data_directory)

    def shelf(self) -> dict[str, object]:
        connection = connect(self._database)
        try:
            return build_shelf(
                self._topics,
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
            path = urlparse(self.path).path
            if path == "/api/shelf":
                self._json(200, backend.shelf())
                return
            self._file(path)

        def do_POST(self) -> None:
            if urlparse(self.path).path != "/api/ask":
                self._json(404, {"error": "Not found."})
                return
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
            self.end_headers()
            self.wfile.write(body)

    return DeskHandler


def _read_json(handler: BaseHTTPRequestHandler) -> object:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > _MAX_BODY:
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
