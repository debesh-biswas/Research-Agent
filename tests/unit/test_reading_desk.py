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


def test_topics_page_is_wired_to_the_topic_endpoints() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert '["topics", "Topics", "#/topics"]' in script
    for hook in ("data-run-topic", "data-toggle-topic", "data-delete-topic", "topic-edit-form"):
        assert hook in script
    assert '"PUT"' in script and "/run`" in script


def test_new_topic_review_edits_keywords_and_settings() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    for hook in ("data-remove-keyword", "new-keyword", "new-topic-review", "settingsFields"):
        assert hook in script
    assert "window.DESK.defaults" in script


def test_running_runs_show_live_progress() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert 'id="run-banner" aria-live="polite"' in script
    for stage in ("plan_queries", "discover", "classify", "analyze", "report", "persist"):
        assert f"{stage}:" in script
    assert "schedulePoll()" in script and "onFormPage()" in script


def test_setup_page_shows_health_checks_and_first_steps() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert 'fetch("/api/health")' in script
    assert 'href="#/setup"' in script and "Create your first topic" in script
    assert "recheck-health" in script


def test_screened_papers_explain_why_each_was_kept_or_dropped() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert "/screened`" in script and 'href="#/screened"' in script
    for reason in ("selected_deep_read", "action_ignore", "below_threshold", "limit_reached"):
        assert f"{reason}:" in script
    assert "Why it's on the shelf" in script


def test_paper_card_shows_setup_related_work_and_the_stored_pdf() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert '"Experimental setup"' in script and '"Related work"' in script
    assert '/pdf" target="_blank"' in script and "Open PDF" in script
