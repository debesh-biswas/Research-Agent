from datetime import date

import pytest
from pydantic import ValidationError

from research_agent.workflow.state import ResearchState
from tests.unit.conftest import TOPIC_ID


def state(**overrides: object) -> ResearchState:
    payload: dict[str, object] = {
        "topic_id": TOPIC_ID,
        "period_start": date(2026, 9, 17),
        "period_end": date(2026, 9, 27),
    }
    payload.update(overrides)
    return ResearchState.model_validate(payload)


def test_a_fresh_state_is_empty_and_running() -> None:
    fresh = state()

    assert (fresh.run_id, fresh.broadened, fresh.status) == (None, False, "running")
    assert fresh.candidates == [] and fresh.parsed_paths == {}


def test_paths_are_accepted() -> None:
    assert (
        state(parsed_paths={"p1": "/data/topics/t/parsed/p1.md"})
        .parsed_paths["p1"]
        .endswith("p1.md")
    )


def test_document_content_in_state_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must be a path"):
        state(parsed_paths={"p1": "## Introduction\nThe whole paper goes here."})

    with pytest.raises(ValidationError, match="must be a path"):
        state(pdf_paths={"p1": "x" * 2000})


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        state(pdf_bytes=b"%PDF-")
