"""Versioned prompt for the weekly synthesis.

The model sees only the analyses this run produced plus a digest of recent history, each paper
labelled with the identifier it must cite, so a finding can be checked against the corpus.
"""

from research_agent.config import TopicSettings
from research_agent.domain.analysis import PaperAnalysis, SynthesisDraft, WeeklySynthesis

PROMPT_VERSION = "weekly_synthesis.v2"
"""v2: a week too large for one prompt is synthesized in batches, then merged (see MERGE_*)."""

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
What it covers: {description}
Topic keywords: {keywords}
Reporting period: {start} to {end}

This week's analysed papers:
{papers}

{history}"""

_NO_HISTORY = "No previous synthesis exists for this topic, so there is no history to compare with."
BATCH_ENTRIES = 4
MERGED_ENTRIES = 8
"""Caps that keep the merge prompt inside the budget and the merged report readable."""

_LATER_HISTORY = (
    "These papers are one batch of a larger week; another step compares the week with history, "
    "so leave changes_from_history empty. Give at most "
    f"{BATCH_ENTRIES} entries in each of the first five fields: the most important in this batch."
)

MERGE_SYSTEM_PROMPT = (
    "You merge partial syntheses of one research week into a single synthesis. Each partial "
    "covers a different batch of the same week's papers. Reply with JSON only, in the same form "
    'as the partials: {"major_developments": [{"text": "...", "supporting_paper_ids": ["..."]}], '
    '"emerging_directions": [...], "methods_gaining_attention": [...], "contradictions": [...], '
    '"common_limitations": [...], "new_datasets": ["..."], "new_benchmarks": ["..."], '
    '"changes_from_history": ["..."]}. '
    "Combine findings that say the same thing into one and keep the union of their paper ids. "
    f"Keep distinct findings, at most {MERGED_ENTRIES} in each of the first five fields, ranked by "
    "importance across the whole week. Add a "
    "contradiction where partials disagree. Copy paper ids exactly; never invent one. Use "
    "changes_from_history only for what differs from the previous periods shown. Add no fields."
)

_MERGE_TEMPLATE = """Topic: {name}
What it covers: {description}
Reporting period: {start} to {end}

Partial syntheses, one per batch of this week's papers:
{partials}

{history}"""
_TRUNCATED = "\n\n[input truncated; further papers were omitted]"


def render(
    topic: TopicSettings,
    analyses: list[PaperAnalysis],
    titles: dict[str, str],
    history: list[WeeklySynthesis],
    start: str,
    end: str,
    max_input_chars: int,
    *,
    batched: bool = False,
) -> str:
    """Render the synthesis prompt, bounded so a large week cannot overrun the context window.

    `batched` marks one batch of a larger week: history is then left to the merge step.
    """
    papers = "\n\n".join(_paper(analysis, titles) for analysis in analyses)
    return _bounded(
        _fill(topic, start, end, papers, _LATER_HISTORY if batched else _history(history)),
        max_input_chars,
    )


def batches(
    topic: TopicSettings,
    analyses: list[PaperAnalysis],
    titles: dict[str, str],
    history: list[WeeklySynthesis],
    start: str,
    end: str,
    max_input_chars: int,
) -> list[list[PaperAnalysis]]:
    """Split a week into groups whose prompts each fit, in order; one group when it all fits.

    A single paper longer than the budget still gets a group of its own and is truncated there,
    exactly as the unbatched prompt would truncate it.
    """
    whole = _fill(topic, start, end, "", _history(history))
    blocks = [len(_paper(analysis, titles)) + 2 for analysis in analyses]
    if len(whole) + sum(blocks) <= max_input_chars:
        return [list(analyses)]
    room = max_input_chars - len(_fill(topic, start, end, "", _LATER_HISTORY))
    groups: list[list[PaperAnalysis]] = []
    used = 0
    for analysis, size in zip(analyses, blocks, strict=True):
        if groups and used + size <= room:
            groups[-1].append(analysis)
            used += size
        else:
            groups.append([analysis])
            used = size
    return groups


def render_merge(
    topic: TopicSettings,
    partials: list[SynthesisDraft],
    history: list[WeeklySynthesis],
    start: str,
    end: str,
    max_input_chars: int,
) -> str:
    """The merge prompt: every partial's findings with their paper ids, plus the history."""
    sections = []
    for number, partial in enumerate(partials, start=1):
        lines = [f"Batch {number}:"]
        for field in (
            "major_developments",
            "emerging_directions",
            "methods_gaining_attention",
            "contradictions",
            "common_limitations",
        ):
            for finding in getattr(partial, field):
                ids = ", ".join(finding.supporting_paper_ids)
                lines.append(f"  {field}: {finding.text} [{ids}]")
        for field in ("new_datasets", "new_benchmarks"):
            values = getattr(partial, field)
            if values:
                lines.append(f"  {field}: {'; '.join(values)}")
        sections.append("\n".join(lines))
    prompt = _MERGE_TEMPLATE.format(
        name=topic.name,
        description=topic.description.strip() or "not described",
        start=start,
        end=end,
        partials="\n\n".join(sections),
        history=_history(history),
    )
    return _bounded(prompt, max_input_chars)


def _fill(topic: TopicSettings, start: str, end: str, papers: str, history: str) -> str:
    return _TEMPLATE.format(
        name=topic.name,
        description=topic.description.strip() or "not described",
        keywords=", ".join(topic.keywords) if topic.keywords else "none",
        start=start,
        end=end,
        papers=papers,
        history=history,
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
