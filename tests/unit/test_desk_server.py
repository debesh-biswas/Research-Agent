"""The desk server serves the page and the two JSON routes, and refuses paths outside web/."""

import asyncio
import http.client
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from research_agent.config import ApplicationSettings, TopicSettings
from research_agent.desk.ask import DeskLookupError, DeskReply
from research_agent.desk.server import (
    AskRequest,
    LibraryQuery,
    LocalDesk,
    ReadingUpdate,
    TopicSuggestRequest,
    _handler,
)
from research_agent.domain.selection import SelectionDecision, SelectionPlan
from research_agent.models.base import ModelProviderError
from research_agent.operations.health import HealthCheck
from research_agent.operations.locks import RunLocked, lock_path
from research_agent.storage.database import apply_migrations, connect
from research_agent.storage.feedback import SqliteFeedbackRepository
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.reading import ReadingState, SqliteReadingRepository
from research_agent.storage.runs import SqliteRunRepository
from research_agent.storage.selections import SqliteSelectionRepository
from research_agent.storage.topics import (
    SqliteTopicRepository,
    TopicNotFoundError,
    TopicStoreError,
)
from tests.unit.conftest import candidate


class FakeDesk:
    """A desk with no database and no model."""

    def __init__(self) -> None:
        self.created: list[TopicSettings] = []
        self.deleted_runs: list[str] = []
        self.cleared_topics: list[str] = []
        self.updated: list[TopicSettings] = []
        self.deleted_topics: list[str] = []
        self.started: list[str] = []
        self.pdf: Path | None = None
        self.votes: list[tuple[str, str, int]] = []
        self.cleared_threads: list[tuple[str, str | None]] = []

    def shelf(self) -> dict[str, object]:
        return {"live": True, "topics": []}

    async def ask(self, request: AskRequest) -> DeskReply:
        if request.question == "fail":
            raise ModelProviderError("down")
        return DeskReply(
            paragraphs=[f"About {request.topic_id}."],
            cites=[],
            provider="nvidia_nim",
            model="glm-test",
            fell_back=False,
        )

    def thread(self, run_id: str, paper_id: str | None) -> list[dict[str, object]]:
        return [{"question": f"{run_id}/{paper_id}", "paragraphs": ["Yes."], "cites": []}]

    def clear_thread(self, run_id: str, paper_id: str | None) -> int:
        self.cleared_threads.append((run_id, paper_id))
        return 3

    async def suggest(self, request: TopicSuggestRequest) -> list[str]:
        if request.name == "fail":
            raise ModelProviderError("down")
        return [f"{request.name} keyword"]

    def create_and_run(self, topic: TopicSettings) -> None:
        if topic.id == "duplicate":
            raise TopicStoreError("topic already exists")
        self.created.append(topic)

    def delete_run(self, run_id: str) -> None:
        if run_id == "busy-run":
            raise RunLocked("Spatial is running; clear runs after it finishes.")
        self.deleted_runs.append(run_id)

    def clear_topic(self, topic_id: str) -> int:
        if topic_id == "busy":
            raise RunLocked("Busy is running; clear runs after it finishes.")
        self.cleared_topics.append(topic_id)
        return 2

    def storage(self) -> dict[str, object]:
        return {"topics": {"spatial": 1024}, "database": 2048, "free": 10**9}

    def update_topic(self, topic: TopicSettings) -> None:
        if topic.id == "missing":
            raise TopicNotFoundError("unknown topic: missing")
        self.updated.append(topic)

    def delete_topic(self, topic_id: str) -> None:
        if topic_id == "busy":
            raise RunLocked("another run of busy is in progress")
        self.deleted_topics.append(topic_id)

    def run_topic(self, topic_id: str) -> None:
        if topic_id == "paused":
            raise TopicStoreError("Paused is disabled; enable it to run it.")
        self.started.append(topic_id)

    async def health(self) -> list[HealthCheck]:
        return [HealthCheck(name="Local model", status="fail", detail="down", fix="Start it.")]

    def screened(self, run_id: str) -> list[dict[str, object]]:
        return [{"id": "p1", "runId": run_id}]

    def pdf_path(self, paper_id: str) -> Path | None:
        return self.pdf if paper_id == "p1" else None

    def citations(self, run_id: str | None, fmt: str) -> tuple[str, str] | None:
        if run_id not in (None, "r1"):
            return None
        return (f"{run_id or 'saved_papers'}.{fmt}", f"{fmt} for {run_id or 'saved'}\n")

    def run(self, run_id: str) -> dict[str, object] | None:
        return {"id": run_id, "papers": []} if run_id == "old-run" else None

    def library(self, query: LibraryQuery) -> dict[str, object]:
        return {"total": 0, "query": query.model_dump()}

    def report(self, run_id: str) -> tuple[str, str] | None:
        return ("spatial_2026-09-28_weekly_report.md", "# Report\n") if run_id == "r1" else None

    def set_vote(self, topic_id: str, paper_id: str, vote: int) -> None:
        if paper_id != "p1":
            raise DeskLookupError("That paper is not in the library.")
        self.votes.append((topic_id, paper_id, vote))

    def update_reading(self, paper_id: str, update: ReadingUpdate) -> ReadingState:
        if paper_id != "p1":
            raise DeskLookupError("That paper is not in the library.")
        return ReadingState(saved=bool(update.saved), note=update.note or "")


def test_the_server_serves_the_shelf_the_page_and_ask(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<p>desk</p>", encoding="utf-8")
    (web / "fonts").mkdir()
    (web / "fonts" / "a.woff2").write_bytes(b"wOF2")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(FakeDesk(), web.resolve()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/shelf") as response:
            assert json.load(response) == {"live": True, "topics": []}
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
            assert response.read() == b"<p>desk</p>"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/fonts/a.woff2") as response:
            assert (response.headers["Content-Type"], response.read()) == ("font/woff2", b"wOF2")
        body = json.dumps(
            {"question": "What changed?", "topicId": "spatial", "runId": "run-1"}
        ).encode()
        ask = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/ask",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(ask) as response:
            payload = json.load(response)
        assert payload["paragraphs"] == ["About spatial."]
        assert payload["fellBack"] is False
        escaped = urllib.request.Request(f"http://127.0.0.1:{port}/%2e%2e/%2e%2e/etc/passwd")
        with pytest_http_error(escaped) as error:
            assert error.code == 404
        bad = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/ask",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with pytest_http_error(bad) as error:
            assert error.code == 400
        failed = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/ask",
            data=json.dumps({"question": "fail", "topicId": "spatial", "runId": "run-1"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with pytest_http_error(failed) as error:
            assert error.code == 502
        failure = {"question": "fail", "topicId": "spatial", "runId": "run-1"}
        assert _call(f"http://127.0.0.1:{port}", "POST", "/api/ask", failure) == (
            502,
            {
                "error": "The model answered with an error. The setup check shows which model "
                "is failing.",
                "setup": True,
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_the_server_suggests_keywords_and_creates_a_topic(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<p>desk</p>", encoding="utf-8")
    backend = FakeDesk()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(backend, web.resolve()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        suggest = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/topics/suggest",
            data=json.dumps({"name": "Robotics"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(suggest) as response:
            assert json.load(response) == {"keywords": ["Robotics keyword"]}

        failed_suggest = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/topics/suggest",
            data=json.dumps({"name": "fail"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with pytest_http_error(failed_suggest) as error:
            assert error.code == 502

        create = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/topics",
            data=json.dumps({"id": "robotics", "name": "Robotics", "keywords": ["arms"]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(create) as response:
            assert response.status == 202
            assert json.load(response) == {"status": "started", "topicId": "robotics"}
        assert (backend.created[0].id, backend.created[0].keywords) == ("robotics", ["arms"])

        duplicate = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/topics",
            data=json.dumps({"id": "duplicate", "name": "Robotics"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with pytest_http_error(duplicate) as error:
            assert error.code == 409

        advanced = {
            "id": "vision",
            "name": "Vision",
            "lookback_days": 7,
            "discovery": {"openalex": True, "semantic_scholar": False, "arxiv": True},
            "limits": {
                "max_candidates": 100,
                "max_classified": 50,
                "max_downloads": 10,
                "max_deep_reads": 5,
            },
            "scheduling": {"frequency": "weekly", "day": "monday"},
        }
        assert _call(f"http://127.0.0.1:{port}", "POST", "/api/topics", advanced)[0] == 202
        created = backend.created[-1]
        assert (created.lookback_days, created.discovery.semantic_scholar) == (7, False)
        assert (created.limits.max_downloads, created.scheduling.day) == (10, "monday")
        invalid = {**advanced, "id": "bad", "limits": {"max_downloads": 5, "max_deep_reads": 9}}
        assert _call(f"http://127.0.0.1:{port}", "POST", "/api/topics", invalid) == (
            400,
            {"error": "limits: max_deep_reads cannot exceed max_downloads"},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_the_server_clears_a_run_and_a_topic_s_runs(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<p>desk</p>", encoding="utf-8")
    backend = FakeDesk()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(backend, web.resolve()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        delete_run = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/runs/run-123", method="DELETE"
        )
        with urllib.request.urlopen(delete_run) as response:
            assert json.load(response) == {"status": "cleared"}
        assert backend.deleted_runs == ["run-123"]

        clear_topic = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/topics/spatial/runs", method="DELETE"
        )
        with urllib.request.urlopen(clear_topic) as response:
            assert json.load(response) == {"status": "cleared", "runs": 2}
        assert backend.cleared_topics == ["spatial"]
        base = f"http://127.0.0.1:{port}"
        assert _call(base, "DELETE", "/api/runs/busy-run") == (
            409,
            {"error": "Spatial is running; clear runs after it finishes."},
        )
        assert _call(base, "DELETE", "/api/topics/busy/runs")[0] == 409
        assert backend.deleted_runs == ["run-123"]
        assert _call(base, "GET", "/api/storage") == (
            200,
            {"topics": {"spatial": 1024}, "database": 2048, "free": 10**9},
        )

        unknown = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/topics/spatial/papers", method="DELETE"
        )
        with pytest_http_error(unknown) as error:
            assert error.code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class pytest_http_error:
    """Expect urllib to raise HTTPError, which is also a response."""

    def __init__(self, request: urllib.request.Request) -> None:
        self._request = request
        self.code = 0

    def __enter__(self) -> "pytest_http_error":
        try:
            urllib.request.urlopen(self._request)
        except urllib.error.HTTPError as error:
            self.code = error.code
            return self
        raise AssertionError("expected an HTTP error")

    def __exit__(self, *args: object) -> None:
        return None


def test_local_desk_shelf_shows_a_topic_added_after_startup(tmp_path: Path) -> None:
    database = tmp_path / "research_agent.db"
    connection = connect(database)
    apply_migrations(connection)
    desk = LocalDesk(database, ApplicationSettings(data_directory=tmp_path))
    assert desk.shelf()["topics"] == []

    SqliteTopicRepository(connection).add(TopicSettings(id="new_topic", name="New topic"))
    connection.close()

    topics = desk.shelf()["topics"]
    assert isinstance(topics, list)
    assert [topic["id"] for topic in topics] == ["new_topic"]


def test_the_server_refuses_foreign_hosts_and_origins(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<p>desk</p>", encoding="utf-8")
    backend = FakeDesk()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(backend, web.resolve()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"
    create = json.dumps({"id": "robotics", "name": "Robotics"}).encode()
    try:
        rebound = urllib.request.Request(f"{base}/api/shelf", headers={"Host": "evil.example"})
        with pytest_http_error(rebound) as error:
            assert error.code == 403
        cross_site = urllib.request.Request(
            f"{base}/api/topics",
            data=create,
            headers={"Content-Type": "text/plain", "Origin": "https://evil.example"},
        )
        with pytest_http_error(cross_site) as error:
            assert error.code == 403
        cross_delete = urllib.request.Request(
            f"{base}/api/runs/run-1", method="DELETE", headers={"Origin": "null"}
        )
        with pytest_http_error(cross_delete) as error:
            assert error.code == 403
        assert (backend.created, backend.deleted_runs) == ([], [])

        own_page = urllib.request.Request(
            f"{base}/api/topics",
            data=create,
            headers={"Content-Type": "application/json", "Origin": f"http://localhost:{port}"},
        )
        own_page.add_unredirected_header("Host", f"localhost:{port}")
        with urllib.request.urlopen(own_page) as response:
            assert response.status == 202
        assert [topic.id for topic in backend.created] == ["robotics"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _call(base: str, method: str, path: str, body: object | None = None) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        f"{base}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_the_server_edits_deletes_and_runs_topics(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    backend = FakeDesk()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(backend, web.resolve()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        edited = {"name": "Robotics", "lookback_days": 7, "keywords": ["arms"]}
        assert _call(base, "PUT", "/api/topics/robotics", edited) == (200, {"status": "updated"})
        assert [(topic.id, topic.lookback_days) for topic in backend.updated] == [("robotics", 7)]

        bad_limits = {"name": "Robotics", "limits": {"max_downloads": 5, "max_deep_reads": 9}}
        status, payload = _call(base, "PUT", "/api/topics/robotics", bad_limits)
        assert status == 400
        assert payload == {"error": "limits: max_deep_reads cannot exceed max_downloads"}
        assert _call(base, "PUT", "/api/topics/missing", {"name": "X"})[0] == 404
        assert _call(base, "PUT", "/api/topics/robotics", {"name": "X", "colour": "red"})[0] == 400

        assert _call(base, "DELETE", "/api/topics/robotics") == (200, {"status": "deleted"})
        assert _call(base, "DELETE", "/api/topics/busy")[0] == 409
        assert backend.deleted_topics == ["robotics"]

        assert _call(base, "GET", "/api/runs/run-7/screened") == (
            200,
            {"papers": [{"id": "p1", "runId": "run-7"}]},
        )
        backend.pdf = tmp_path / "p1.pdf"
        backend.pdf.write_bytes(b"%PDF-1.4 test")
        with urllib.request.urlopen(f"{base}/api/papers/p1/pdf") as response:
            assert (response.headers["Content-Type"], response.read()) == (
                "application/pdf",
                b"%PDF-1.4 test",
            )
        assert _call(base, "GET", "/api/papers/p2/pdf")[0] == 404
        with urllib.request.urlopen(f"{base}/api/runs/r1/report") as response:
            assert response.headers["Content-Type"] == "text/markdown; charset=utf-8"
            assert response.headers["Content-Disposition"] == (
                'attachment; filename="spatial_2026-09-28_weekly_report.md"'
            )
            assert response.read() == b"# Report\n"
        assert _call(base, "GET", "/api/runs/r2/report")[0] == 404
        assert _call(base, "GET", "/api/runs/old-run") == (200, {"id": "old-run", "papers": []})
        assert _call(base, "GET", "/api/runs/missing")[0] == 404
        status, page = _call(base, "GET", "/api/library?show=saved&offset=25&topic=spatial")
        assert (status, page) == (
            200,
            {
                "total": 0,
                "query": {"topic": "spatial", "show": "saved", "q": "", "offset": 25, "limit": 25},
            },
        )
        assert _call(base, "GET", "/api/library?limit=0")[0] == 400
        assert _call(base, "GET", "/api/library?show=everything")[0] == 400
        with urllib.request.urlopen(f"{base}/api/runs/r1/citations?format=ris") as response:
            assert response.headers["Content-Type"].startswith("application/x-research-info")
            assert response.headers["Content-Disposition"] == 'attachment; filename="r1.ris"'
            assert response.read() == b"ris for r1\n"
        with urllib.request.urlopen(f"{base}/api/saved/citations") as response:
            assert response.headers["Content-Type"].startswith("application/x-bibtex")
            assert response.read() == b"bib for saved\n"
        assert _call(base, "GET", "/api/runs/r1/citations?format=docx")[0] == 400
        assert _call(base, "GET", "/api/runs/r2/citations?format=bib")[0] == 404
        reading = "/api/papers/p1/reading"
        assert _call(base, "PUT", reading, {"saved": True, "note": "Read §4"}) == (
            200,
            {"read": False, "saved": True, "note": "Read §4"},
        )
        assert _call(base, "PUT", reading, {"starred": True})[0] == 400
        assert _call(base, "PUT", "/api/papers/p2/reading", {"read": True})[0] == 404
        vote = "/api/topics/spatial/feedback/p1"
        assert _call(base, "PUT", vote, {"vote": 1}) == (200, {"vote": 1})
        assert _call(base, "PUT", vote, {"vote": 0}) == (200, {"vote": 0})
        assert _call(base, "PUT", vote, {"vote": 2})[0] == 400
        assert _call(base, "PUT", "/api/topics/spatial/feedback/p2", {"vote": 1})[0] == 404
        assert backend.votes == [("spatial", "p1", 1), ("spatial", "p1", 0)]
        assert _call(base, "GET", "/api/health") == (
            200,
            {
                "checks": [
                    {"name": "Local model", "status": "fail", "detail": "down", "fix": "Start it."}
                ]
            },
        )
        assert _call(base, "GET", "/api/runs/r1/ask?paper=p%201") == (
            200,
            {"turns": [{"question": "r1/p 1", "paragraphs": ["Yes."], "cites": []}]},
        )
        assert _call(base, "GET", "/api/runs/r1/ask")[1] == {
            "turns": [{"question": "r1/None", "paragraphs": ["Yes."], "cites": []}]
        }
        assert _call(base, "DELETE", "/api/runs/r1/ask?paper=p1") == (
            200,
            {"status": "cleared", "turns": 3},
        )
        assert _call(base, "DELETE", "/api/runs/r1/ask")[0] == 200
        assert backend.cleared_threads == [("r1", "p1"), ("r1", None)]
        assert backend.deleted_runs == []
        assert _call(base, "POST", "/api/topics/robotics/run", {}) == (202, {"status": "started"})
        status, payload = _call(base, "POST", "/api/topics/paused/run", {})
        assert (status, payload) == (409, {"error": "Paused is disabled; enable it to run it."})
        assert backend.started == ["robotics"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_local_desk_topic_actions_guard_the_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "research_agent.db"
    connection = connect(database)
    apply_migrations(connection)
    topics = SqliteTopicRepository(connection)
    topics.add(TopicSettings(id="live_topic", name="Live"))
    topics.add(TopicSettings(id="paused_topic", name="Paused", enabled=False))
    desk = LocalDesk(database, ApplicationSettings(data_directory=tmp_path))
    started: list[str] = []
    monkeypatch.setattr(desk, "_start_run", lambda topic: started.append(topic.id))

    desk.update_topic(TopicSettings(id="live_topic", name="Live", lookback_days=3))
    stored = topics.get("live_topic")
    assert stored is not None and stored.lookback_days == 3
    assert desk.shelf()["topics"][0]["settings"]["lookback_days"] == 3  # type: ignore[index]

    desk.run_topic("live_topic")
    assert started == ["live_topic"]
    with pytest.raises(TopicStoreError, match="disabled"):
        desk.run_topic("paused_topic")
    with pytest.raises(TopicNotFoundError):
        desk.run_topic("missing")
    SqliteRunRepository(connection).start("live_topic")
    with pytest.raises(RunLocked, match="already running"):
        desk.run_topic("live_topic")

    lock = lock_path(tmp_path, "paused_topic")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("not a pid", encoding="utf-8")
    with pytest.raises(RunLocked):
        desk.delete_topic("paused_topic")
    lock.unlink()
    desk.delete_topic("paused_topic")
    assert [topic.id for topic in topics.list()] == ["live_topic"]
    connection.close()


def test_a_kept_alive_connection_survives_routes_that_ignore_or_reject_a_body(
    tmp_path: Path,
) -> None:
    web = tmp_path / "web"
    web.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(FakeDesk(), web.resolve()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
    json_headers = {"Content-Type": "application/json"}
    try:
        # One connection, as a browser keeps it: bodies no route reads must not leak forward.
        for method, path in (("POST", "/api/topics/robotics/run"), ("DELETE", "/api/runs/r1")):
            connection.request(method, path, body="{}", headers=json_headers)
            connection.getresponse().read()
        connection.request("GET", "/api/shelf")
        response = connection.getresponse()
        assert (response.status, json.load(response)) == (200, {"live": True, "topics": []})

        connection.request("POST", "/api/ask", body="x" * 20_000, headers=json_headers)
        rejected = connection.getresponse()
        rejected.read()
        assert (rejected.status, rejected.getheader("Connection")) == (400, "close")
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_local_desk_serves_only_pdfs_inside_the_library(tmp_path: Path) -> None:
    database = tmp_path / "research_agent.db"
    connection = connect(database)
    apply_migrations(connection)
    papers = SqlitePaperRepository(connection)
    desk = LocalDesk(database, ApplicationSettings(data_directory=tmp_path / "library"))
    inside = tmp_path / "library" / "topics" / "t" / "pdfs" / "inside.pdf"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(b"%PDF")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"%PDF")
    not_pdf = inside.with_suffix(".txt")
    not_pdf.write_text("secret", encoding="utf-8")
    files = {
        "inside": inside,
        "outside": outside,
        "not_pdf": not_pdf,
        "gone": inside.with_name("gone.pdf"),
    }
    ids = {}
    for title, path in files.items():
        ids[title] = papers.upsert(candidate(title=title, doi=f"10.1000/{title}"))
        papers.record_file(ids[title], "pdf", str(path), 4, "0" * 64)
    connection.close()

    found = {title: desk.pdf_path(paper_id) for title, paper_id in ids.items()}

    assert found == {"inside": inside.resolve(), "outside": None, "not_pdf": None, "gone": None}
    assert desk.pdf_path("no_such_paper") is None


def test_local_desk_merges_reading_changes_and_shows_them_on_the_shelf(tmp_path: Path) -> None:
    database = tmp_path / "research_agent.db"
    connection = connect(database)
    apply_migrations(connection)
    paper_id = SqlitePaperRepository(connection).upsert(candidate(title="Maps", doi="10.1/m"))
    connection.close()
    desk = LocalDesk(database, ApplicationSettings(data_directory=tmp_path))

    desk.update_reading(paper_id, ReadingUpdate(read=True))
    state = desk.update_reading(paper_id, ReadingUpdate(note="Compare with last week."))

    assert state == ReadingState(read=True, saved=False, note="Compare with last week.")
    with pytest.raises(DeskLookupError):
        desk.update_reading("no_such_paper", ReadingUpdate(saved=True))


def test_local_desk_records_votes_that_reach_the_shelf(tmp_path: Path) -> None:
    database = tmp_path / "research_agent.db"
    connection = connect(database)
    apply_migrations(connection)
    SqliteTopicRepository(connection).add(TopicSettings(id="spatial", name="Spatial"))
    paper_id = SqlitePaperRepository(connection).upsert(candidate(title="Maps", doi="10.1/m"))
    desk = LocalDesk(database, ApplicationSettings(data_directory=tmp_path))

    desk.set_vote("spatial", paper_id, 1)
    votes = SqliteFeedbackRepository(connection)
    assert votes.votes_for("spatial", [paper_id]) == {paper_id: 1}
    desk.set_vote("spatial", paper_id, 0)
    assert votes.votes_for("spatial", [paper_id]) == {}
    with pytest.raises(DeskLookupError):
        desk.set_vote("no_topic", paper_id, 1)
    with pytest.raises(DeskLookupError):
        desk.set_vote("spatial", "no_paper", -1)
    connection.close()


def test_a_client_that_hangs_up_mid_reply_is_not_a_server_error(tmp_path: Path) -> None:
    class HungUp:
        def write(self, data: bytes) -> int:
            raise BrokenPipeError(32, "Broken pipe")

        def flush(self) -> None:
            raise BrokenPipeError(32, "Broken pipe")

    handler_class = _handler(FakeDesk(), tmp_path)
    handler = handler_class.__new__(handler_class)
    handler.request_version = "HTTP/1.1"
    handler.requestline = "GET /api/shelf HTTP/1.1"
    handler.command, handler.path = "GET", "/api/shelf"
    handler.close_connection = False
    handler.wfile = HungUp()  # type: ignore[assignment]

    handler._json(200, {"live": True})  # type: ignore[attr-defined]  # must not raise

    assert handler.close_connection is True


def test_local_desk_exports_a_runs_kept_papers_and_all_saved_ones(tmp_path: Path) -> None:
    database = tmp_path / "research_agent.db"
    connection = connect(database)
    apply_migrations(connection)
    SqliteTopicRepository(connection).add(TopicSettings(id="spatial", name="Spatial"))
    papers = SqlitePaperRepository(connection)
    kept = papers.upsert(candidate(title="Topological Maps", doi="10.1/kept"))
    dropped = papers.upsert(candidate(title="Click Rates", doi="10.1/dropped"))
    run = SqliteRunRepository(connection).start("spatial")
    SqliteSelectionRepository(connection).save(
        run.id,
        SelectionPlan(
            decisions=[
                SelectionDecision(
                    paper_id=kept,
                    rank=1,
                    selected=True,
                    action="deep_read",
                    reason="selected_deep_read",
                ),
                SelectionDecision(
                    paper_id=dropped,
                    rank=2,
                    selected=False,
                    action="ignore",
                    reason="action_ignore",
                ),
            ]
        ),
    )
    SqliteReadingRepository(connection).save(dropped, ReadingState(saved=True))
    connection.close()
    desk = LocalDesk(database, ApplicationSettings(data_directory=tmp_path))

    name, bib = desk.citations(run.id, "bib") or ("", "")
    assert name == f"spatial_{run.started_at.date().isoformat()}_papers.bib"
    assert "Topological Maps" in bib and "Click Rates" not in bib
    saved_name, ris = desk.citations(None, "ris") or ("", "")
    assert saved_name == "saved_papers.ris"
    assert "TI  - Click Rates" in ris and "Topological" not in ris
    assert desk.citations("no_such_run", "bib") is None


def test_local_desk_serves_an_old_run_and_a_library_page(tmp_path: Path) -> None:
    database = tmp_path / "research_agent.db"
    connection = connect(database)
    apply_migrations(connection)
    SqliteTopicRepository(connection).add(TopicSettings(id="spatial", name="Spatial"))
    paper_id = SqlitePaperRepository(connection).upsert(candidate(title="Maps", doi="10.1/m"))
    run = SqliteRunRepository(connection).start("spatial")
    SqliteSelectionRepository(connection).save(
        run.id,
        SelectionPlan(
            decisions=[
                SelectionDecision(
                    paper_id=paper_id,
                    rank=1,
                    selected=True,
                    action="summarize",
                    reason="selected_summarize",
                )
            ]
        ),
    )
    connection.close()
    desk = LocalDesk(database, ApplicationSettings(data_directory=tmp_path))

    shelf_run = desk.run(run.id)
    assert shelf_run is not None
    kept = shelf_run["papers"]
    assert isinstance(kept, list) and [card["id"] for card in kept] == [paper_id]
    assert desk.run("missing") is None
    page = desk.library(LibraryQuery())
    assert page["total"] == 1
    row = page["papers"][0]  # type: ignore[index]
    assert (row["title"], row["topicName"], row["runId"]) == ("Maps", "Spatial", run.id)


def test_local_desk_sends_earlier_turns_and_keeps_each_thread_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "research_agent.db"
    connection = connect(database)
    apply_migrations(connection)
    SqliteTopicRepository(connection).add(TopicSettings(id="spatial", name="Spatial"))
    run = SqliteRunRepository(connection).start("spatial")
    seen: list[list[tuple[str, list[str]]]] = []

    async def fake_answer(*_: object, question: str, history: object, **__: object) -> DeskReply:
        seen.append(list(history))  # type: ignore[call-overload]
        if question == "fail":
            raise ModelProviderError("down", "MODEL_TIMEOUT")
        return DeskReply(paragraphs=[f"On {question}."], provider="local", model="m")

    monkeypatch.setattr("research_agent.desk.server.answer_question", fake_answer)
    desk = LocalDesk(database, ApplicationSettings(data_directory=tmp_path))

    def ask(question: str, paper: str | None = None) -> None:
        request = AskRequest(question=question, topicId="spatial", runId=run.id, paperId=paper)
        asyncio.run(desk.ask(request))

    ask("first")
    ask("second")
    ask("about the paper", "p1")
    with pytest.raises(ModelProviderError):
        ask("fail")

    assert seen == [
        [],
        [("first", ["On first."])],
        [],
        [("first", ["On first."]), ("second", ["On second."])],
    ]
    assert [turn["question"] for turn in desk.thread(run.id, None)] == ["first", "second"]
    assert desk.thread(run.id, "p1") == [
        {
            "question": "about the paper",
            "paragraphs": ["On about the paper."],
            "cites": [],
            "note": "",
        }
    ]
    assert desk.clear_thread(run.id, None) == 2
    assert desk.thread(run.id, None) == []
    assert len(desk.thread(run.id, "p1")) == 1
    desk.delete_run(run.id)
    assert connection.execute("SELECT COUNT(*) FROM ask_turns").fetchone()[0] == 0
    connection.close()


def test_local_desk_clears_a_runs_own_files_but_never_a_running_topic(tmp_path: Path) -> None:
    database = tmp_path / "research_agent.db"
    connection = connect(database)
    apply_migrations(connection)
    SqliteTopicRepository(connection).add(TopicSettings(id="spatial", name="Spatial"))
    runs = SqliteRunRepository(connection)
    old, same_day, newest = (runs.start("spatial") for _ in range(3))
    days = {old.id: "2026-10-01", same_day.id: "2026-10-20", newest.id: "2026-10-20"}
    for run_id, day in days.items():
        connection.execute(
            "UPDATE runs SET started_at = ? WHERE id = ?", (f"{day}T09:00:00+00:00", run_id)
        )
    connection.commit()
    topic = tmp_path / "topics" / "spatial"
    for folder, name in [
        ("runs", f"{old.id}-manifest.json"),
        ("runs", f"{old.id}-ideation.md"),
        ("runs", f"{newest.id}-manifest.json"),
        ("reports", "2026-10-01_weekly_report.md"),
        ("reports", "2026-10-20_weekly_report.md"),
        ("papers", "arxiv_1.pdf"),
    ]:
        (topic / folder).mkdir(parents=True, exist_ok=True)
        (topic / folder / name).write_text("x" * 10, encoding="utf-8")
    desk = LocalDesk(database, ApplicationSettings(data_directory=tmp_path))

    def left() -> set[str]:
        return {path.name for path in topic.rglob("*") if path.is_file()}

    desk.delete_run(old.id)
    assert left() == {"2026-10-20_weekly_report.md", f"{newest.id}-manifest.json", "arxiv_1.pdf"}
    desk.delete_run(same_day.id)
    assert "2026-10-20_weekly_report.md" in left(), "the newest run still shows that report"

    usage = desk.storage()
    assert usage["topics"] == {"spatial": 30}
    assert usage["database"] > 0 and usage["free"] > 0  # type: ignore[operator]

    lock = lock_path(tmp_path, "spatial")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
    with pytest.raises(RunLocked, match="Spatial is running"):
        desk.delete_run(newest.id)
    with pytest.raises(RunLocked):
        desk.clear_topic("spatial")
    assert runs.get(newest.id) is not None
    lock.unlink()

    assert desk.clear_topic("spatial") == 1
    assert left() == {"arxiv_1.pdf"}
    assert runs.recent("spatial") == [] and SqliteTopicRepository(connection).get("spatial")
    desk.delete_run("missing")
    connection.close()
