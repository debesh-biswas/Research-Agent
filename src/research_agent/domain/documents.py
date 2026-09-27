"""Structured output of a parsed paper (TRD section 22).

Provider-neutral: nothing here knows which parser produced it, so a different backend changes one
adapter rather than every consumer.
"""

from pydantic import Field

from research_agent.config import StrictModel


class ParsedSection(StrictModel):
    """One titled block of body text, in document order."""

    title: str | None = None
    text: str = ""
    page: int | None = Field(default=None, ge=1)


class ParsedTable(StrictModel):
    caption: str | None = None
    rows: list[list[str]] = Field(default_factory=list)
    page: int | None = Field(default=None, ge=1)


class ParsedFigure(StrictModel):
    caption: str | None = None
    page: int | None = Field(default=None, ge=1)


class ParsedReference(StrictModel):
    text: str = Field(min_length=1)


class ParsedPaper(StrictModel):
    """A paper's readable content, ready for analysis, plus the provenance to reproduce it."""

    paper_id: str = Field(min_length=1)
    source_pdf_path: str = Field(min_length=1)
    title: str | None = None
    sections: list[ParsedSection] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    figures: list[ParsedFigure] = Field(default_factory=list)
    references: list[ParsedReference] = Field(default_factory=list)
    parser_name: str = Field(min_length=1)
    parser_version: str | None = None

    @property
    def text(self) -> str:
        """The body text an analysis prompt reads, with section titles kept as headings."""
        blocks = [
            f"## {section.title}\n{section.text}".strip() if section.title else section.text.strip()
            for section in self.sections
        ]
        return "\n\n".join(block for block in blocks if block)
