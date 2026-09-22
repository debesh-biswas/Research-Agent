import json
import logging

import pytest

from research_agent.observability import configure_logging


def test_json_logging_includes_context(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")

    logging.getLogger("test").info(
        "paper classified",
        extra={"run_id": "run-1", "paper_id": "paper-1", "status": "success"},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["level"] == "INFO"
    assert payload["message"] == "paper classified"
    assert payload["run_id"] == "run-1"
    assert payload["paper_id"] == "paper-1"
    assert payload["status"] == "success"
    assert payload["timestamp"].endswith("+00:00")
