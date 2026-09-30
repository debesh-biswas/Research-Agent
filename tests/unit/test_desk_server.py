"""The desk server serves the page and the two JSON routes, and refuses paths outside web/."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from research_agent.desk.ask import DeskReply
from research_agent.desk.server import (
    AskRequest,
    TopicCreateRequest,
    TopicSuggestRequest,
    _handler,
)
from research_agent.models.base import ModelProviderError
from research_agent.storage.topics import TopicStoreError


class FakeDesk:
    """A desk with no database and no model."""

    def __init__(self) -> None:
        self.created: list[TopicCreateRequest] = []

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

    def create_and_run(self, request: TopicCreateRequest) -> None:
        if request.topic_id == "duplicate":
            raise TopicStoreError("topic already exists")
        self.created.append(request)


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
        assert backend.created[0].topic_id == "robotics"

        duplicate = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/topics",
            data=json.dumps({"id": "duplicate", "name": "Robotics"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with pytest_http_error(duplicate) as error:
            assert error.code == 409
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
