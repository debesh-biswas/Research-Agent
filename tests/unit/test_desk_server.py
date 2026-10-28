"""The desk server serves the page and the two JSON routes, and refuses paths outside web/."""

import http.client
import json
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
    LocalDesk,
    ReadingUpdate,
    TopicSuggestRequest,
    _handler,
)
from research_agent.models.base import ModelProviderError
from research_agent.operations.health import HealthCheck
from research_agent.operations.locks import RunLocked, lock_path
from research_agent.storage.database import apply_migrations, connect
from research_agent.storage.feedback import SqliteFeedbackRepository
from research_agent.storage.papers import SqlitePaperRepository
from research_agent.storage.reading import ReadingState
from research_agent.storage.runs import SqliteRunRepository
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

    async def suggest(self, request: TopicSuggestRequest) -> list[str]:
        if request.name == "fail":
            raise ModelProviderError("down")
        return [f"{request.name} keyword"]

    def create_and_run(self, topic: TopicSettings) -> None:
        if topic.id == "duplicate":
            raise TopicStoreError("topic already exists")
        self.created.append(topic)

    def delete_run(self, run_id: str) -> None:
        self.deleted_runs.append(run_id)

    def clear_topic(self, topic_id: str) -> int:
        self.cleared_topics.append(topic_id)
        return 2

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
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(FakeDesk(), web.resolve()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/shelf") as response:
            assert json.load(response) == {"live": True, "topics": []}
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
            assert response.read() == b"<p>desk</p>"
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
