"""The real Docling adapter over a committed PDF fixture.

Marked `slow` and deselected by default: Docling loads a large ML stack and downloads model
weights on first use. Run explicitly with `uv run pytest -m slow`, which needs network the first
time. Deselected, not skipped, so the suite never pretends this ran.
"""

from pathlib import Path

import pytest

from research_agent.documents.docling_parser import DoclingParser

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "documents" / "sample.pdf"

pytestmark = pytest.mark.slow


def test_a_real_pdf_yields_text_and_parser_provenance() -> None:
    parsed = DoclingParser().parse(FIXTURE, "fixture_paper")

    assert parsed.paper_id == "fixture_paper"
    assert parsed.parser_name == "docling"
    assert parsed.parser_version is not None
    assert parsed.sections, "the fixture has body text, so at least one section is expected"
    assert "embodied agents" in parsed.text


def test_the_same_pdf_parses_identically_twice() -> None:
    parser = DoclingParser()

    first = parser.parse(FIXTURE, "fixture_paper")
    second = parser.parse(FIXTURE, "fixture_paper")

    assert first.text == second.text


def test_a_corrupt_pdf_raises_rather_than_returning_empty_output(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\nnot actually a pdf")

    with pytest.raises(Exception):  # noqa: B017 - Docling's own exception type is not part of our contract
        DoclingParser().parse(broken, "broken_paper")
