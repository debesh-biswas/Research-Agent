"""Versioned prompt for the weekly synthesis.

The model sees only the analyses this run produced plus a digest of recent history, each paper
labelled with the identifier it must cite, so a finding can be checked against the corpus.
"""

from research_agent.config import TopicSettings
from research_agent.domain.analysis import PaperAnalysis, WeeklySynthesis

PROMPT_VERSION = "weekly_synthesis.v1"

SYSTEM_PROMPT = (
    "You compare this week's analysed papers for one research topic. Reply with JSON only, in the "
    'form {"major_developments": [{"text": "...", "supporting_paper_ids": ["..."]}], '
    '"emerging_directions": [...], "methods_gaining_attention": [...], "contradictions": [...], '
    '"common_limitations": [...], "new_datasets": ["..."], "new_benchmarks": ["..."], '
    '"changes_from_history": ["..."]}. '
    "Every entry of the first five fields must cite at least one supporting paper id, copied "
    "exactly from the ids given below; a statement you cannot attribute must be left out. "
    "Use changes_from_history only for what differs from the previous periods shown, and leave it "
    "empty when no history is given. Add no fields beyond the ones listed."
)

_TEMPLATE = """Topic: {name}
Topic keywords: {keywords}
Reporting period: {start} to {end}

This week's analysed papers:
{papers}

{history}"""

_NO_HISTORY = "No previous synthesis exists for this topic, so there is no history to compare with."
_TRUNCATED = "\n\n[input truncated; further papers were omitted]"


def render(
    topic: TopicSettings,
    analyses: list[PaperAnalysis],
    titles: dict[str, str],
    history: list[WeeklySynthesis],
    start: str,
    end: str,
    max_input_chars: int,
) -> str:
    """Render the synthesis prompt, bounded so a large week cannot overrun the context window."""
    papers = "\n\n".join(_paper(analysis, titles) for analysis in analyses)
    return _bounded(
        _TEMPLATE.format(
            name=topic.name,
            keywords=", ".join(topic.keywords) if topic.keywords else "none",
            start=start,
            end=end,
            papers=papers,
            history=_history(history),
        ),
        max_input_chars,
    )


def _paper(analysis: PaperAnalysis, titles: dict[str, str]) -> str:
    lines = [
        f"- id: {analysis.paper_id}",
        f"  title: {titles.get(analysis.paper_id, 'unknown')}",
        f"  contribution: {analysis.main_contribution}",
        f"  method: {analysis.method}",
    ]
    if analysis.main_results:
        lines.append(f"  results: {'; '.join(analysis.main_results)}")
    if analysis.limitations:
        lines.append(f"  limitations: {'; '.join(analysis.limitations)}")
    if analysis.datasets:
        lines.append(f"  datasets: {', '.join(analysis.datasets)}")
    if analysis.benchmarks:
        lines.append(f"  benchmarks: {', '.join(analysis.benchmarks)}")
    if analysis.abstract_only:
        lines.append("  depth: abstract only, so treat its detail as uncertain")
    return "\n".join(lines)


def _history(history: list[WeeklySynthesis]) -> str:
    if not history:
        return _NO_HISTORY
    periods = []
    for index, synthesis in enumerate(history, start=1):
        developments = [finding.text for finding in synthesis.major_developments]
        directions = [finding.text for finding in synthesis.emerging_directions]
        periods.append(
            f"Period -{index}:\n"
            f"  developments: {'; '.join(developments) or 'none recorded'}\n"
            f"  directions: {'; '.join(directions) or 'none recorded'}"
        )
    return "Previous periods, newest first:\n" + "\n".join(periods)


def _bounded(prompt: str, max_input_chars: int) -> str:
    if len(prompt) <= max_input_chars:
        return prompt
    return prompt[:max_input_chars] + _TRUNCATED
