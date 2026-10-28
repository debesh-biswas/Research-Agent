"""The reading desk is a static page, served live with no sample-data fallback."""

import re
from pathlib import Path

import pytest

from research_agent import cli

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


def test_papers_track_read_saved_and_notes() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert "/reading`" in script and "markReadOnOpen" in script
    for hook in ("data-toggle-saved", "data-toggle-read", "note-form", "noteDrafts"):
        assert hook in script
    assert 'filterButton("unread"' in script and 'filterButton("saved"' in script


def test_relevance_votes_are_offered_on_papers_and_screened_rows() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert "/feedback/" in script and "castVote" in script
    assert script.count("voteButtons(") >= 3, (
        "defined once, used on the paper page and screened rows"
    )


def test_the_report_can_be_downloaded_and_printed() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    css = (WEB / "css" / "desk.css").read_text(encoding="utf-8")
    assert '/report" download>Download Markdown' in script
    assert "window.print()" in script
    assert "@media print" in css and "@page" in css


def test_papers_page_exports_citations() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert "/citations`" in script and '"/api/saved/citations"' in script
    assert "?format=${format}" in script


def test_a_finished_run_notifies_a_reader_who_is_away() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert "Notification.requestPermission()" in script and "askToNotify();" in script
    assert "document.hidden" in script and "notifyFinished(state.finishedNotice.text)" in script


def test_library_lists_every_kept_paper_and_opens_older_runs() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert '["library", "Library", "#/library"]' in script
    assert "/api/library?" in script and "/api/runs/${encodeURIComponent(runId)}`" in script
    assert "keepOlderRuns()" in script and "data-library-page" in script
    assert "brand-action" not in script, "New topic lives on the Topics and welcome pages"


def test_library_search_is_debounced_and_keeps_the_caret() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert 'id="library-search"' in script and 'params.set("q"' in script
    assert "librarySearchTimer = setTimeout" in script and "setSelectionRange" in script


def test_destructive_actions_confirm_in_a_dialog_and_short_calls_time_out() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert "confirm(" not in script.replace("confirmAction(", ""), "no native confirm() left"
    assert "dialog.showModal()" in script and 'value="cancel" autofocus' in script
    assert "AbortSignal.timeout(REQUEST_MS)" in script
    assert 'await request("/api/shelf")' in script


def test_fonts_are_self_hosted_with_their_licences() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "googleapis" not in html and "gstatic" not in html, "no third-party request"
    assert 'href="fonts/fonts.css"' in html and 'href="favicon.svg"' in html
    css = (WEB / "fonts" / "fonts.css").read_text(encoding="utf-8")
    files = set(re.findall(r'url\("([^"]+)"\)', css))
    assert files and all((WEB / "fonts" / name).is_file() for name in files)
    for family in ("ibm-plex-mono", "literata", "schibsted-grotesk"):
        assert "SIL Open Font License" in (WEB / "fonts" / f"OFL-{family}.txt").read_text()
    assert (WEB / "favicon.svg").is_file()


def test_a_single_day_period_is_not_written_as_a_range() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert "run.periodStart === run.periodEnd" in script


def test_the_desk_finds_its_page_from_any_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert cli._web_root() == WEB


def test_the_wheel_ships_the_desk_page() -> None:
    pyproject = (WEB.parent / "pyproject.toml").read_text(encoding="utf-8")

    assert '"web" = "research_agent/web"' in pyproject


def test_settings_page_is_linked_and_never_sends_locked_fields() -> None:
    script = (WEB / "js" / "desk.js").read_text(encoding="utf-8")
    assert 'href="#/settings"' in script and 'request("/api/settings")' in script
    assert "if (input.disabled) continue;" in script
