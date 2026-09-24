"""Docling adapter (TRD section 22).

The only module that imports Docling. Its heavy dependencies load when a parser is constructed,
not when the package is imported, so the rest of the suite never pays for them.
"""

from pathlib import Path
from typing import Any

from research_agent.domain.documents import (
    ParsedFigure,
    ParsedPaper,
    ParsedReference,
    ParsedSection,
    ParsedTable,
)

_SECTION_LABELS = frozenset({"text", "paragraph", "list_item", "code", "formula", "footnote"})
_HEADING_LABELS = frozenset({"section_header", "title"})
_REFERENCE_HEADINGS = ("reference", "bibliography", "works cited")


class DoclingParser:
    """Convert a PDF with Docling and translate its document model into `ParsedPaper`."""

    name = "docling"

    def __init__(self, converter: Any = None) -> None:
        if converter is None:
            # Imported here so `import research_agent` never drags in torch.
            from docling.document_converter import DocumentConverter

            converter = DocumentConverter()
        self._converter = converter
        self._version = _installed_version()

    def parse(self, pdf_path: Path, paper_id: str) -> ParsedPaper:
        """Parse one PDF. Docling failures propagate; `ParsingService` turns them into outcomes."""
        document = self._converter.convert(str(pdf_path)).document
        sections, references = _sections_and_references(document)
        return ParsedPaper(
            paper_id=paper_id,
            source_pdf_path=str(pdf_path),
            title=_title(document),
            sections=sections,
            tables=_tables(document),
            figures=_figures(document),
            references=references,
            parser_name=self.name,
            parser_version=self._version,
        )


def _installed_version() -> str | None:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("docling")
    except PackageNotFoundError:
        return None


def _text(item: Any) -> str:
    return (getattr(item, "text", "") or "").strip()


def _page(item: Any) -> int | None:
    provenance = getattr(item, "prov", None) or []
    page = getattr(provenance[0], "page_no", None) if provenance else None
    return page if isinstance(page, int) and page >= 1 else None


def _label(item: Any) -> str:
    label = getattr(item, "label", "")
    return str(getattr(label, "value", label))


def _title(document: Any) -> str | None:
    """Prefer an explicit title item; real papers often only mark it as the first heading."""
    first_heading: str | None = None
    for item in getattr(document, "texts", []):
        label, text = _label(item), _text(item)
        if not text:
            continue
        if label == "title":
            return text
        if first_heading is None and label == "section_header":
            first_heading = text
    return first_heading


def _sections_and_references(document: Any) -> tuple[list[ParsedSection], list[ParsedReference]]:
    """Walk the text items once, folding body text under the heading that precedes it.

    Anything under a references heading becomes a `ParsedReference` instead of body text, because
    a bibliography is provenance rather than content to analyze.
    """
    sections: list[ParsedSection] = []
    references: list[ParsedReference] = []
    heading: str | None = None
    buffer: list[str] = []
    page: int | None = None
    in_references = False

    def flush() -> None:
        nonlocal buffer
        if buffer:
            sections.append(ParsedSection(title=heading, text="\n".join(buffer), page=page))
            buffer = []

    for item in getattr(document, "texts", []):
        label, text = _label(item), _text(item)
        if not text:
            continue
        if label in _HEADING_LABELS:
            flush()
            heading = text
            page = _page(item)
            in_references = any(marker in text.casefold() for marker in _REFERENCE_HEADINGS)
            continue
        if label not in _SECTION_LABELS:
            continue
        if in_references:
            references.append(ParsedReference(text=text))
        else:
            buffer.append(text)
    flush()
    return sections, references


def _tables(document: Any) -> list[ParsedTable]:
    tables: list[ParsedTable] = []
    for table in getattr(document, "tables", []):
        rows: list[list[str]] = []
        try:
            frame = table.export_to_dataframe(document)
            rows = [[str(cell) for cell in row] for row in frame.values.tolist()]
        except Exception:
            rows = []
        tables.append(ParsedTable(caption=_caption(table, document), rows=rows, page=_page(table)))
    return tables


def _figures(document: Any) -> list[ParsedFigure]:
    return [
        ParsedFigure(caption=_caption(picture, document), page=_page(picture))
        for picture in getattr(document, "pictures", [])
    ]


def _caption(item: Any, document: Any) -> str | None:
    try:
        caption = item.caption_text(document)
    except Exception:
        return None
    return caption.strip() or None if isinstance(caption, str) else None
