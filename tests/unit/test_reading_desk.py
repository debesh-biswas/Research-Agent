"""The reading desk is a static page. These checks keep its entry points and sample shelf intact."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web"


def test_desk_page_loads_its_assets() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "css/desk.css" in html
    assert "js/data.js" in html
    assert "js/desk.js" in html


def test_desk_routes_cover_the_reading_surfaces() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    for route in ("week", "papers", "report", "runs", "ask"):
        assert route in script
    assert "NVIDIA NIM is not connected yet" in script


def test_sample_shelf_has_both_topics_and_paper_cards() -> None:
    data = (WEB / "js" / "data.js").read_text(encoding="utf-8")
    assert "embodied_spatial_intelligence" in data
    assert "computer_vision" in data
    for field in ("executiveSummary", "readingOrder", "abstractOnly", "claims"):
        assert field in data
