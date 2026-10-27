"""Building a Docling parser must not load Docling; the first parse does, once."""

import sys
import types

import pytest

from research_agent.documents.docling_parser import DoclingParser


def test_docling_loads_on_first_use_not_on_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    built: list[object] = []

    class FakeConverter:
        def __init__(self) -> None:
            built.append(self)

    module = types.ModuleType("docling.document_converter")
    module.DocumentConverter = FakeConverter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "docling.document_converter", module)

    parser = DoclingParser()
    assert built == [], "a run must open without paying for Docling"

    first = parser._ready_converter()
    assert parser._ready_converter() is first
    assert built == [first]
