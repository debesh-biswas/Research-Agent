"""The reading desk is a static page, served live with no sample-data fallback."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web"


def test_desk_page_loads_its_assets() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "css/desk.css" in html
    assert "js/desk.js" in html
    assert "data.js" not in html


def test_desk_routes_cover_the_reading_surfaces() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    for route in ("week", "papers", "report", "runs", "ask", "new"):
        assert route in script
    assert "Can't reach the desk server" in script
    assert "/api/shelf" in script
    assert "/api/ask" in script
    assert "/api/topics" in script


def test_clearing_data_is_wired_to_the_run_and_topic_endpoints() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert "/api/runs/" in script
    assert "/api/topics/" in script
    assert "data-clear-run" in script
    assert "clear-topic-runs" in script
