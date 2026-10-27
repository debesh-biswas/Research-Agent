"""Versioned prompt for the report's one piece of model-written prose.

Only the executive summary is model-assisted; every other section is assembled deterministically
from stored records, so a provider failure costs a paragraph rather than the report.
"""

from pydantic import Field

from research_agent.config import StrictModel, TopicSettings
from research_agent.domain.analysis import WeeklySynthesis

PROMPT_VERSION = "report_summary.v1"

SYSTEM_PROMPT = (
    "You write the executive summary of a weekly research intelligence report. Reply with JSON "
    'only, in the form {"executive_summary": "..."}. Write three to six sentences of plain prose '
    "for a researcher who will read the rest of the report underneath it. Use only the findings "
    "given; do not add papers, numbers, or claims that are not there. Do not use Markdown headings "
    "or bullet points. Add no fields beyond the one listed."
)

_TEMPLATE = """Topic: {name}
Reporting period: {start} to {end}
Papers analysed this period: {papers}

Findings:
{findings}"""


class ReportProse(StrictModel):
    """The only part of a report a model writes."""

    executive_summary: str = Field(min_length=1)


def render(
    topic: TopicSettings,
    synthesis: WeeklySynthesis | None,
    papers: int,
    start: str,
    end: str,
    max_input_chars: int,
) -> str:
    return _bounded(
        _TEMPLATE.format(
            name=topic.name,
            start=start,
            end=end,
            papers=papers,
            findings=_findings(synthesis),
        ),
        max_input_chars,
    )


def _findings(synthesis: WeeklySynthesis | None) -> str:
    if synthesis is None:
        return "no synthesis was produced for this period"
    lines = [
        f"- {label}: {finding.text}"
        for label, findings in (
            ("development", synthesis.major_developments),
            ("direction", synthesis.emerging_directions),
            ("method", synthesis.methods_gaining_attention),
            ("contradiction", synthesis.contradictions),
            ("limitation", synthesis.common_limitations),
        )
        for finding in findings
    ]
    lines.extend(
        f"- change from previous periods: {change}" for change in synthesis.changes_from_history
    )
    return "\n".join(lines) or "the synthesis recorded no findings"


def _bounded(prompt: str, max_input_chars: int) -> str:
    if len(prompt) <= max_input_chars:
        return prompt
    return prompt[:max_input_chars] + "\n\n[input truncated]"
